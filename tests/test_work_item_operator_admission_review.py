from sentientos.work_item_operator_admission_review import OperatorAdmissionReviewPolicy, OperatorAdmissionReviewRequest, evaluate_operator_admission_review


def _dossier(status='promotion_ready_for_admission_review', **over):
    d = {
        'promotion_dossier_id':'wip_1','promotion_dossier_digest':'abc','work_item_id':'w1','source_kind':'ticket','source_ref':'X-1',
        'promotion_status': status,'review_packet_id':'wir_1','review_packet_digest':'r1','risk_class':'low','contradiction_codes':[],
        'blocker_codes':[],'warning_codes':[],'artifact_records':[{'digest':'d1'}],'missing_metadata_fields':[]
    }
    d.update(over)
    return d


def test_status_mapping() -> None:
    assert evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier())).status == 'admission_review_ready'
    assert evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier('promotion_ready_with_warnings'))).status == 'admission_review_ready_with_warnings'
    assert evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier('promotion_requires_manual_review'))).status == 'admission_review_manual_review_required'
    assert evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier('promotion_requires_clarification'))).status == 'admission_review_requires_clarification'
    assert evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier('promotion_blocked_authority'))).status == 'admission_review_blocked'
    assert evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier('promotion_insufficient_evidence'))).status == 'admission_review_insufficient_evidence'


def test_policy_and_mismatch() -> None:
    req = OperatorAdmissionReviewRequest(promotion_dossier=_dossier('promotion_ready_with_warnings'))
    assert evaluate_operator_admission_review(req, policy=OperatorAdmissionReviewPolicy(allow_warning_review=False)).status == 'admission_review_manual_review_required'
    mismatch = evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier(), review_packet={'source_work_item_id':'other'}))
    assert mismatch.status == 'admission_review_contradicted'


def test_candidate_command_only_when_ready() -> None:
    ready = evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier())).packet
    blocked = evaluate_operator_admission_review(OperatorAdmissionReviewRequest(promotion_dossier=_dossier('promotion_blocked_authority'))).packet
    assert ready.candidate_manual_command and 'not authorization' in ready.candidate_manual_command
    assert blocked.candidate_manual_command is None
