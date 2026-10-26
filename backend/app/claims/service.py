"""Orchestrate the six stages of one claim check. Nothing about the student is stored.

1. Extract receipt facts.  2. Identify the product and the edition for each service date.
3. Retrieve evidence per aspect.  4. Read conditions, verify them, and decide in code.
5. Calculate in code.  6. Explain the supported outcome, with citations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from sqlalchemy.orm import Session

from app.claims import repository
from app.claims.catalog import (
  DOCUMENTS_BY_ID,
  INSURERS,
  INSURERS_BY_ID,
  PRODUCTS_BY_ID,
  PolicyDocument,
  PolicyProduct,
  document_for,
  products_for,
)
from app.claims.estimate import estimate_benefit, money
from app.claims.evaluation import (
  NEED_ORDER,
  EffectiveLine,
  effective_lines,
  evaluate_line,
  where,
)
from app.claims.operations import (
  ClaimsOperations,
  message_numbers_supported,
  verify_condition,
)
from app.claims.readiness import receipt_issues, with_plausible_dates
from app.claims.retrieval import LineEvidence, ServiceQuery, retrieve_evidence
from app.claims.schemas import (
  OUTCOME_LABELS,
  AnswerInput,
  AssessedLine,
  AssessmentState,
  ClaimAnswers,
  ClaimResponse,
  ClaimStep,
  Condition,
  ConditionDraft,
  ConditionKind,
  ConditionState,
  LineConditionsDraft,
  LineResult,
  NextQuestion,
  Outcome,
  PolicyContext,
  PolicyEdition,
  QuestionOption,
  ReceiptFacts,
  ReceiptIssue,
  ServiceCategory,
  Slot,
)
from app.config import load_azure_openai_settings
from app.providers import AzureOpenAIError, AzureOpenAIProvider

FINAL_NOTE = "Your insurer makes the final decision."
OTHER_INSURER = "other"
UNSURE_PRODUCT = "unsure"


class NotHealthReceiptError(ValueError):
  """The uploaded file is not a receipt for a health service or product."""


class KnowledgeBaseMissingError(RuntimeError):
  """A policy edition the answer needs has not been ingested yet."""


class InvalidClaimRequestError(ValueError):
  """The request names an unknown insurer or product, or a tampered assessment."""


class StaleAssessmentError(ValueError):
  """The receipt details changed since the assessment, so it must be redone."""


@lru_cache(maxsize=1)
def get_claims_operations() -> ClaimsOperations:
  """Build and cache the model operations behind the claim checker."""
  return ClaimsOperations(AzureOpenAIProvider(load_azure_openai_settings()))


def extract_receipt(
  document_bytes: bytes,
  mime_type: str,
) -> tuple[ReceiptFacts, tuple[ReceiptIssue, ...]]:
  """Stage 1: read printed facts in memory and flag anything unclear."""
  today = date.today()
  facts = with_plausible_dates(
    get_claims_operations().read_receipt(document_bytes, mime_type),
    today,
  )
  _require_health_receipt(facts)
  return facts, receipt_issues(facts, today)


def assess_claim(session: Session, facts: ReceiptFacts, answers: ClaimAnswers) -> ClaimResponse:
  """Stages 2-6: ask for missing policy facts, or retrieve, read, and decide."""
  _require_health_receipt(facts)
  question = _policy_question(answers)
  if question is not None:
    return question
  product = PRODUCTS_BY_ID[str(answers.product_id)]
  lines = effective_lines(facts, answers)
  undated = next((line for line in lines if line.service_date is None), None)
  if undated is not None:
    return _ask(_question(Slot.SERVICE_DATE, undated, product))

  documents = _documents(product, lines)
  assessable = [line for line in lines if documents[line.line_index] is not None]
  _require_ingested(session, {_document(documents, line).id for line in assessable})
  operations = get_claims_operations()
  evidence = retrieve_evidence(
    session,
    operations.embed,
    [
      ServiceQuery(
        line_index=line.line_index,
        document_id=_document(documents, line).id,
        scope=product.scope,
        service_text=service_text(line, facts),
      )
      for line in assessable
    ],
  )
  drafts = (
    {
      draft.line_index: draft
      for draft in operations.extract_conditions(
        _conditions_payload(product, facts, assessable, evidence, documents)
      ).lines
    }
    if assessable
    else {}
  )
  state = AssessmentState(
    product_id=product.id,
    lines=tuple(
      _verified_line(line, item, drafts.get(line.line_index), _document(documents, line))
      for line, item in zip(assessable, evidence, strict=True)
    ),
  )
  return _respond(product, lines, state, documents, answers)


def reassess_claim(
  session: Session,
  facts: ReceiptFacts,
  answers: ClaimAnswers,
  state: AssessmentState,
) -> ClaimResponse:
  """Re-verify a returned assessment against the stored policy text, then decide again."""
  _require_health_receipt(facts)
  question = _policy_question(answers)
  if question is not None:
    return question
  product = PRODUCTS_BY_ID[str(answers.product_id)]
  if state.product_id != product.id:
    raise StaleAssessmentError("The product changed since this receipt was checked.")
  lines = effective_lines(facts, answers)
  by_index = {line.line_index: line for line in lines}
  documents = _documents(product, lines)
  chunks = repository.chunks_by_id(
    session,
    [condition.chunk_id for assessed in state.lines for condition in assessed.conditions],
  )
  for assessed in state.lines:
    line = by_index.get(assessed.line_index)
    document = documents.get(assessed.line_index)
    if (
      line is None
      or document is None
      or document.id != assessed.document_id
      or line.description != assessed.description
      or line.service_date != assessed.service_date
    ):
      raise StaleAssessmentError("The receipt details changed since this receipt was checked.")
    for condition in assessed.conditions:
      chunk = chunks.get(condition.chunk_id)
      if (
        chunk is None
        or chunk.document_id != document.id
        or (product.scope is not None and chunk.scopes and product.scope not in chunk.scopes)
        or verify_condition(_as_draft(condition), chunk, document.title) != condition
      ):
        raise InvalidClaimRequestError(
          "The returned assessment does not match the stored policy text."
        )
  return _respond(product, lines, state, documents, answers)


def interpret_answer(question: NextQuestion, text: str) -> str | None:
  """Map a typed reply onto a question's format, or None when it does not answer it."""
  reply = " ".join(text.split())
  if question.input == AnswerInput.TEXT:
    return reply or None
  value = get_claims_operations().interpret({
    "question": question.prompt,
    "input": question.input.value,
    "options": [{"value": option.value, "label": option.label} for option in question.options],
    "reply": reply,
  })
  return _valid_answer(question, value)


def policy_catalog(session: Session) -> list[dict[str, object]]:
  """Describe every insurer, product, and edition, and whether each edition is ingested."""
  ingested = repository.ingested_documents(session)
  return [
    {
      "id": insurer.id,
      "name": insurer.name,
      "products": [
        {
          "id": product.id,
          "name": product.name,
          "editions": [
            {
              "document_id": document_id,
              "title": DOCUMENTS_BY_ID[document_id].title,
              "effective_basis": DOCUMENTS_BY_ID[document_id].effective_basis,
              "ingested": document_id in ingested,
            }
            for document_id in product.document_ids
          ],
        }
        for product in products_for(insurer.id)
      ],
    }
    for insurer in INSURERS
  ]


def _require_health_receipt(facts: ReceiptFacts) -> None:
  if not facts.is_health_receipt:
    raise NotHealthReceiptError(f"This does not look like a health receipt: {facts.reason}")


def _require_ingested(session: Session, document_ids: set[str]) -> None:
  missing = document_ids - repository.ingested_documents(session).keys()
  if missing:
    raise KnowledgeBaseMissingError(
      "These policy editions are not loaded yet: "
      f"{', '.join(sorted(missing))}. Run scripts/ingest_policy.py."
    )


def _policy_question(answers: ClaimAnswers) -> ClaimResponse | None:
  """Stage 2 first needs the insurer, then the product; neither is ever guessed."""
  if answers.insurer_id is None:
    return _ask(NextQuestion(
      slot=Slot.INSURER,
      prompt="Which OSHC insurer covers you?",
      input=AnswerInput.CHOICE,
      options=(
        *(QuestionOption(value=insurer.id, label=insurer.name) for insurer in INSURERS),
        QuestionOption(value=OTHER_INSURER, label="Another insurer"),
      ),
    ))
  if answers.insurer_id == OTHER_INSURER:
    return ClaimResponse(
      stage="result",
      message=(
        "This checker only knows nib, Bupa, and Allianz Care OSHC policies so far, so it "
        f"cannot check this receipt against your insurer's terms. {FINAL_NOTE}"
      ),
      next_question=None,
    )
  insurer = INSURERS_BY_ID.get(answers.insurer_id)
  if insurer is None:
    raise InvalidClaimRequestError("That insurer is not in the catalog.")
  product_question = NextQuestion(
    slot=Slot.PRODUCT,
    prompt=(
      f"Which {insurer.name} product do you have? It is on your membership card or "
      "certificate of insurance."
    ),
    input=AnswerInput.CHOICE,
    options=(
      *(
        QuestionOption(value=product.id, label=product.name)
        for product in products_for(insurer.id)
      ),
      QuestionOption(value=UNSURE_PRODUCT, label="Not sure"),
    ),
  )
  if answers.product_id is None:
    return _ask(product_question)
  if answers.product_id == UNSURE_PRODUCT:
    return ClaimResponse(
      stage="question",
      message=(
        "Your product name is printed on your membership card, your certificate of "
        f"insurance, or in the {insurer.name} app. Choose it when you have it."
      ),
      next_question=product_question,
    )
  product = PRODUCTS_BY_ID.get(answers.product_id)
  if product is None or product.insurer_id != insurer.id:
    raise InvalidClaimRequestError("That product does not belong to the chosen insurer.")
  return None


def _ask(question: NextQuestion) -> ClaimResponse:
  return ClaimResponse(stage="question", message=question.prompt, next_question=question)


def _documents(
  product: PolicyProduct,
  lines: list[EffectiveLine],
) -> dict[int, PolicyDocument | None]:
  """Pick the edition governing each line's service date (None when not loaded)."""
  return {
    line.line_index: (
      document_for(product, line.service_date) if line.service_date is not None else None
    )
    for line in lines
  }


def _document(documents: dict[int, PolicyDocument | None], line: EffectiveLine) -> PolicyDocument:
  document = documents[line.line_index]
  if document is None:
    raise InvalidClaimRequestError("A line without a policy edition cannot be assessed.")
  return document


def service_text(line: EffectiveLine, facts: ReceiptFacts) -> str:
  """What retrieval searches for one line: its description, item code, and provider type."""
  parts = (line.description, line.item_code, facts.provider_type.value)
  return " ".join(part for part in parts if part)


def _conditions_payload(
  product: PolicyProduct,
  facts: ReceiptFacts,
  lines: list[EffectiveLine],
  evidence: list[LineEvidence],
  documents: dict[int, PolicyDocument | None],
) -> dict[str, object]:
  """Everything the model may read: public line facts and the retrieved passages only."""
  return {
    "product": product.name,
    "provider_type": facts.provider_type.value,
    "lines": [
      {
        "line_index": line.line_index,
        "policy": _document(documents, line).title,
        "service": line.description,
        "item_code": line.item_code,
        "service_date": line.service_date.isoformat() if line.service_date else None,
        "amount_charged": str(line.amount_charged) if line.amount_charged is not None else None,
        "aspects_without_evidence": [aspect.value for aspect in item.missing_aspects],
        "passages": [
          {
            "chunk_id": chunk.id,
            "retrieved_for": [
              aspect.value
              for aspect, group in item.passages.items()
              if any(member.id == chunk.id for member in group)
            ],
            "section": " ".join(
              part for part in (chunk.section_number, chunk.section_title) if part
            ),
            "pages": (
              str(chunk.page_start)
              if chunk.page_start == chunk.page_end
              else f"{chunk.page_start}-{chunk.page_end}"
            ),
            "text": chunk.text,
          }
          for chunk in item.chunks().values()
        ],
      }
      for line, item in zip(lines, evidence, strict=True)
    ],
  }


def _verified_line(
  line: EffectiveLine,
  evidence: LineEvidence,
  draft: LineConditionsDraft | None,
  document: PolicyDocument,
) -> AssessedLine:
  """Keep only conditions whose quotes are really in this line's retrieved passages."""
  chunks = evidence.chunks()
  conditions: list[Condition] = []
  seen: set[tuple[str, int, str]] = set()
  for condition_draft in draft.conditions if draft is not None else ():
    chunk = chunks.get(condition_draft.chunk_id)
    if chunk is None:
      continue
    condition = verify_condition(condition_draft, chunk, document.title)
    if condition is None:
      continue
    key = (condition.kind.value, condition.chunk_id, condition.citation.quote.casefold())
    if key not in seen:
      seen.add(key)
      conditions.append(condition)
  return AssessedLine(
    line_index=line.line_index,
    document_id=document.id,
    service_date=line.service_date or date.min,
    description=line.description or "",
    category=draft.category if draft is not None else ServiceCategory.OTHER,
    description_specific_enough=draft.description_specific_enough if draft else True,
    conditions=tuple(conditions),
    missing_aspects=evidence.missing_aspects,
  )


def _as_draft(condition: Condition) -> ConditionDraft:
  return ConditionDraft(
    kind=condition.kind,
    applies=condition.applies,
    months=condition.months,
    percent=condition.percent,
    amount=condition.amount,
    period=condition.period,
    basis=condition.basis,
    detail=condition.detail,
    exception=condition.exception,
    chunk_id=condition.chunk_id,
    quote=condition.citation.quote,
  )


def _respond(
  product: PolicyProduct,
  lines: list[EffectiveLine],
  state: AssessmentState,
  documents: dict[int, PolicyDocument | None],
  answers: ClaimAnswers,
) -> ClaimResponse:
  """Stages 4-6: decide each line in code, calculate, then explain."""
  today = date.today()
  assessed = {line.line_index: line for line in state.lines}
  pools = _limit_pools(state)
  # One answer covers every line sharing an annual limit; the pool is drawn down in order.
  answers = answers.model_copy(update={"benefits_used": {
    **answers.benefits_used,
    **{
      member: used
      for members in pools.values()
      if (used := next(
        (answers.benefits_used[m] for m in members if m in answers.benefits_used),
        None,
      )) is not None
      for member in members
    },
  }})
  drawn: dict[int, Decimal] = {leader: Decimal("0") for leader in pools}
  pool_of = {member: leader for leader, members in pools.items() for member in members}
  results: list[LineResult] = []
  for line in lines:
    item = assessed.get(line.line_index)
    if item is None:
      results.append(LineResult(
        line_index=line.line_index,
        description=line.description,
        amount_paid=line.amount_paid,
        outcome=Outcome.MORE_INFORMATION_NEEDED,
        reasons=(
          f"No {product.name} policy edition covering {line.service_date} is loaded, so "
          "this service cannot be checked.",
        ),
        needs=(),
        conditions=(),
        estimate=None,
      ))
      continue
    evaluation = evaluate_line(line, item, answers, today)
    leader = pool_of.get(line.line_index)
    used = answers.benefits_used.get(line.line_index)
    if leader is not None and used is not None:
      used += drawn[leader]
    estimate = (
      estimate_benefit(line.amount_paid, item.conditions, used)
      if evaluation.outcome == Outcome.APPEARS_ELIGIBLE and line.amount_paid is not None
      else None
    )
    if leader is not None and estimate is not None and estimate.amount is not None:
      drawn[leader] += estimate.amount
    results.append(LineResult(
      line_index=line.line_index,
      description=line.description,
      amount_paid=line.amount_paid,
      outcome=evaluation.outcome,
      reasons=evaluation.reasons,
      needs=evaluation.needs,
      conditions=evaluation.results,
      estimate=estimate,
    ))

  next_question = _next_question(results, lines, product, assessed)
  return ClaimResponse(
    stage="question" if next_question is not None else "result",
    message=_message(product, results, next_question),
    next_question=next_question,
    lines=tuple(results),
    claim_steps=_claim_steps(state),
    policy=_policy_context(product, documents),
    state=state,
  )


def _limit_pools(state: AssessmentState) -> dict[int, list[int]]:
  """Group lines that share one annual-limit clause, keyed by the first such line."""
  pools: dict[tuple[int, Decimal], list[int]] = {}
  for assessed in sorted(state.lines, key=lambda line: line.line_index):
    for condition in assessed.conditions:
      if (
        condition.kind == ConditionKind.ANNUAL_LIMIT
        and condition.applies
        and condition.amount is not None
      ):
        members = pools.setdefault((condition.chunk_id, condition.amount), [])
        if assessed.line_index not in members:
          members.append(assessed.line_index)
        break
  return {members[0]: members for members in pools.values()}


def _next_question(
  results: list[LineResult],
  lines: list[EffectiveLine],
  product: PolicyProduct,
  assessed: dict[int, AssessedLine],
) -> NextQuestion | None:
  by_index = {line.line_index: line for line in lines}
  for slot in NEED_ORDER:
    for result in results:
      if slot in result.needs:
        item = assessed.get(result.line_index)
        return _question(
          slot,
          by_index[result.line_index],
          product,
          item.category if item is not None else None,
        )
  return None


def _question(
  slot: Slot,
  line: EffectiveLine,
  product: PolicyProduct,
  category: ServiceCategory | None = None,
) -> NextQuestion:
  service = f"“{line.description}”" if line.description else f"line {line.line_index + 1}"
  if slot == Slot.SERVICE_DATE:
    return NextQuestion(
      slot=slot,
      line_index=line.line_index,
      prompt=f"The service date for {service} is unclear. What date was it?",
      input=AnswerInput.DATE,
    )
  if slot == Slot.SERVICE_DESCRIPTION:
    return NextQuestion(
      slot=slot,
      line_index=line.line_index,
      prompt=(
        f"The receipt only says {service}. What was this service, for example an eye "
        "test, new glasses, or a GP visit?"
      ),
      input=AnswerInput.TEXT,
    )
  if slot == Slot.COVER_START_DATE:
    return NextQuestion(
      slot=slot,
      prompt=(
        f"When did your {product.name} cover start? It is on your certificate of insurance."
      ),
      input=AnswerInput.DATE,
    )
  if slot == Slot.HAS_REFERRAL:
    return NextQuestion(
      slot=slot,
      line_index=line.line_index,
      prompt=f"Did a doctor refer you for {service}?",
      input=AnswerInput.YES_NO,
      options=(
        QuestionOption(value="yes", label="Yes"),
        QuestionOption(value="no", label="No"),
      ),
    )
  if slot == Slot.BENEFITS_USED:
    kind = (category or ServiceCategory.OTHER).value.replace("_", " ")
    return NextQuestion(
      slot=slot,
      line_index=line.line_index,
      prompt=(
        f"How much has {product.name} already paid you this year for {kind}? Enter 0 if "
        "nothing."
      ),
      input=AnswerInput.AMOUNT,
      options=(QuestionOption(value="0", label="Nothing yet"),),
    )
  return NextQuestion(
    slot=Slot.AMOUNT_PAID,
    line_index=line.line_index,
    prompt=f"How much did you pay for {service}?",
    input=AnswerInput.AMOUNT,
  )


def _message(
  product: PolicyProduct,
  results: list[LineResult],
  next_question: NextQuestion | None,
) -> str:
  """Stage 6: let the model explain, but only with numbers already in its payload."""
  payload: dict[str, object] = {
    "product": product.name,
    "lines": [
      {
        "service": result.description,
        "amount_paid": money(result.amount_paid) if result.amount_paid is not None else None,
        "outcome": OUTCOME_LABELS[result.outcome],
        "reasons": list(result.reasons),
        "deciding_passages": [
          {"where": where(item.condition), "quote": item.condition.citation.quote}
          for item in result.conditions
          if item.state != ConditionState.INFORMATION
        ],
        "estimate_steps": list(result.estimate.steps) if result.estimate else [],
        "estimate_note": result.estimate.note if result.estimate else None,
      }
      for result in results
    ],
    "next_question": next_question.prompt if next_question is not None else None,
  }
  try:
    message = get_claims_operations().write_message(payload)
  except AzureOpenAIError:
    message = ""
  if not message or not message_numbers_supported(message, payload):
    message = _template(results, next_question)
  return f"{message} {FINAL_NOTE}"


def _template(results: list[LineResult], next_question: NextQuestion | None) -> str:
  """A deterministic explanation used whenever the model's message cannot be trusted."""
  sentences: list[str] = []
  for result in results:
    paid = f" ({money(result.amount_paid)})" if result.amount_paid is not None else ""
    sentences.append(
      f"{result.description or 'This service'}{paid}: {OUTCOME_LABELS[result.outcome]}."
    )
    sentences.extend(result.reasons[:2])
    if result.estimate is not None and result.estimate.amount is not None:
      sentences.append(f"Estimate: {'; '.join(result.estimate.steps)}.")
    elif result.estimate is not None and result.estimate.note:
      sentences.append(result.estimate.note)
  if next_question is not None:
    sentences.append(next_question.prompt)
  return " ".join(sentences)


def _claim_steps(state: AssessmentState) -> tuple[ClaimStep, ...]:
  steps: list[ClaimStep] = []
  seen: set[str] = set()
  for assessed in state.lines:
    for condition in assessed.conditions:
      if condition.kind == ConditionKind.CLAIM_TIME_LIMIT and condition.months is not None:
        text = f"Lodge the claim within {condition.months} months of the service date."
      elif condition.kind in {ConditionKind.CLAIM_DOCUMENT, ConditionKind.PROVIDER_REQUIREMENT}:
        text = condition.detail or ""
      else:
        continue
      if text and text.casefold() not in seen:
        seen.add(text.casefold())
        steps.append(ClaimStep(text=text, citation=condition.citation))
  return tuple(steps)


def _policy_context(
  product: PolicyProduct,
  documents: dict[int, PolicyDocument | None],
) -> PolicyContext:
  used = {document.id: document for document in documents.values() if document is not None}
  return PolicyContext(
    insurer=INSURERS_BY_ID[product.insurer_id].name,
    product=product.name,
    editions=tuple(
      PolicyEdition(
        document_id=document.id,
        title=document.title,
        effective_basis=document.effective_basis,
      )
      for document in used.values()
    ),
  )


def _valid_answer(question: NextQuestion, value: str | None) -> str | None:
  """Accept an interpreted reply only in the exact format the question expects."""
  if value is None:
    return None
  value = value.strip()
  if question.input == AnswerInput.CHOICE:
    return value if value in {option.value for option in question.options} else None
  if question.input == AnswerInput.YES_NO:
    return value.casefold() if value.casefold() in {"yes", "no"} else None
  if question.input == AnswerInput.DATE:
    try:
      parsed = date.fromisoformat(value)
    except ValueError:
      return None
    return parsed.isoformat() if parsed <= date.today() else None
  try:
    amount = Decimal(value)
  except InvalidOperation:
    return None
  return str(amount) if Decimal("0") <= amount <= Decimal("100000") else None
