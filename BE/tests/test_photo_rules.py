"""Phase 4b pure rules: product photos, QC (BR-21) and acceptance (BR-13, FR-28). No database."""
from datetime import datetime, timedelta, timezone

import pytest

from app.domain import photo_rules as pr
from app.models.ops import JobStatus

MB = 1024 * 1024
V = pr.PhotoView


def _code(fn, *a, **kw) -> str:
    with pytest.raises(pr.PhotoRuleError) as e:
        fn(*a, **kw)
    return e.value.code


# ---- BR-21 -------------------------------------------------------------------------------------------
def test_two_passing_photos_with_both_kinds_are_enough():
    pr.check_ready_for_submission([V("OVERALL", "PASS"), V("CLOSE_UP", "PASS")])
    pr.check_ready_for_submission([V("OVERALL", "PASS"), V("CLOSE_UP", "PASS"), V("OTHER", "PASS")])


@pytest.mark.parametrize("photos,expect", [
    ([], {"photos": 0}),
    ([V("OVERALL", "PASS")], {"photos": 1}),                                          # only one photo
    ([V("OVERALL", "PASS"), V("OVERALL", "PASS")], {"missing_kinds": ["CLOSE_UP"]}),  # two photos, no close-up
    ([V("CLOSE_UP", "PASS"), V("OTHER", "PASS")], {"missing_kinds": ["OVERALL"]}),
    ([V("OVERALL", "PASS"), V("CLOSE_UP", "FAIL")], {"failed": 1}),                   # one failed photo blocks
    ([V("OVERALL", "PASS"), V("CLOSE_UP", None)], {"unchecked": 1}),                  # QC not done yet
    ([V("OVERALL", "PASS"), V("CLOSE_UP", "PASS"), V("OTHER", "FAIL")], {"failed": 1}),  # the DB guard checks every photo
])
def test_submission_is_refused_until_the_requirements_are_met(photos, expect):
    with pytest.raises(pr.PhotoRuleError) as e:
        pr.check_ready_for_submission(photos)
    assert e.value.code == "PHOTO_REQUIREMENTS_NOT_MET"
    assert all(e.value.details[k] == v for k, v in expect.items()), e.value.details


def test_failed_qc_needs_a_note():
    pr.check_qc_note("PASS", None)
    pr.check_qc_note("FAIL", "mực loang")
    for note in (None, "", "  ", "ab"):
        assert _code(pr.check_qc_note, "FAIL", note) == "QC_NOTE_REQUIRED"


# ---- upload checks -----------------------------------------------------------------------------------
def test_upload_request_limits():
    pr.check_upload_request("image/jpeg", 5 * MB, 20 * MB, 0)
    pr.check_upload_request("image/png", 20 * MB, 20 * MB, pr.MAX_PHOTOS_PER_JOB - 1)
    assert _code(pr.check_upload_request, "application/pdf", 1, 20 * MB, 0) == "INVALID_PHOTO"
    assert _code(pr.check_upload_request, "image/gif", 1, 20 * MB, 0) == "INVALID_PHOTO"
    assert _code(pr.check_upload_request, "image/jpeg", 20 * MB + 1, 20 * MB, 0) == "FILE_TOO_LARGE"
    assert _code(pr.check_upload_request, "image/jpeg", 0, 20 * MB, 0) == "FILE_TOO_LARGE"
    assert _code(pr.check_upload_request, "image/jpeg", 1, 20 * MB, pr.MAX_PHOTOS_PER_JOB) == "TOO_MANY_PHOTOS"


def test_uploaded_object_is_judged_by_its_real_content():
    pr.check_image("image/jpeg", 3 * MB, 20 * MB, 1920, 1080)
    pr.check_image("image/png", 3 * MB, 20 * MB, 1280, 100)                           # only the long side counts
    assert _code(pr.check_image, None, 10, 20 * MB, 2000, 2000) == "INVALID_PHOTO"    # not an image at all
    assert _code(pr.check_image, "application/pdf", 10, 20 * MB, 2000, 2000) == "INVALID_PHOTO"
    assert _code(pr.check_image, "image/jpeg", 10, 20 * MB, None, None) == "INVALID_PHOTO"   # bytes that do not decode
    assert _code(pr.check_image, "image/jpeg", 21 * MB, 20 * MB, 2000, 2000) == "FILE_TOO_LARGE"
    assert _code(pr.check_image, "image/jpeg", 10, 20 * MB, 1279, 800) == "PHOTO_TOO_SMALL"


def test_photo_keys_and_paths_are_built_by_the_server():
    good = "a" * 32 + ".jpg"
    assert pr.is_valid_key(good) and pr.is_valid_key("0123456789abcdef0123456789abcdef.png")
    for bad in ("", "../../etc/passwd", "a" * 32, "a" * 32 + ".pdf", "A" * 32 + ".jpg", "a" * 31 + ".jpg", good + "/x"):
        assert not pr.is_valid_key(bad), bad
    assert pr.object_path(7, 9, good) == f"orders/7/product/9/{good}"
    assert pr.extension("image/jpeg") == "jpg" and pr.extension("image/png") == "png"


# ---- job transitions of this step ----------------------------------------------------------------------
def test_step_transitions_and_production_names():
    assert pr.can_step(JobStatus.WRITTEN, JobStatus.PHOTO_UPLOADED)
    assert pr.can_step(JobStatus.WRITTEN, JobStatus.REWRITE_REQUIRED)               # QC failed
    assert pr.can_step(JobStatus.PHOTO_UPLOADED, JobStatus.DONE)                    # accepted
    assert pr.can_step(JobStatus.PHOTO_UPLOADED, JobStatus.REWRITE_REQUIRED)        # customer asked for a rewrite
    for src, dst in ((JobStatus.WRITTEN, JobStatus.DONE), (JobStatus.WRITING, JobStatus.PHOTO_UPLOADED),
                     (JobStatus.DONE, JobStatus.REWRITE_REQUIRED), (JobStatus.REWRITE_REQUIRED, JobStatus.WRITTEN),
                     (JobStatus.PHOTO_UPLOADED, JobStatus.WRITTEN), (JobStatus.FAILED, JobStatus.PHOTO_UPLOADED)):
        assert not pr.can_step(src, dst), (src, dst)
    assert pr.production_name(JobStatus.DONE) == "FINISHED"
    assert pr.production_name(JobStatus.PHOTO_UPLOADED) == "PHOTO_UPLOADED"
    assert pr.production_name(JobStatus.REWRITE_REQUIRED) == "REWRITE_REQUIRED"


# ---- acceptance deadline (FR-28) ----------------------------------------------------------------------
def test_acceptance_deadline_and_overdue():
    t0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    assert pr.acceptance_deadline(t0, 7) == t0 + timedelta(days=7)
    assert not pr.is_overdue(t0, t0 + timedelta(days=7) - timedelta(seconds=1), 7)
    assert pr.is_overdue(t0, t0 + timedelta(days=7), 7)
    assert pr.is_overdue(t0, t0 + timedelta(days=30), 7)
    assert not pr.is_overdue(None, t0 + timedelta(days=30), 7)                      # never started waiting
    assert not pr.is_overdue(t0, t0 + timedelta(days=8), 30)                        # the setting is honoured


# ---- BR-13 ---------------------------------------------------------------------------------------------
def test_only_one_free_rewrite():
    pr.check_rewrite_allowed(False)
    assert _code(pr.check_rewrite_allowed, True) == "REWRITE_LIMIT_REACHED"


def test_rewrite_reason_must_be_one_of_the_two_causes_and_explained():
    pr.check_rewrite_reason("WORKSHOP_ERROR", "Nét bị đứt ở dòng 2")
    pr.check_rewrite_reason("DIFFERS_FROM_SKETCH", "Khác phác thảo")
    assert _code(pr.check_rewrite_reason, "CHANGED_MY_MIND", "Tôi đổi ý rồi") == "INVALID_REWRITE_REASON"
    for note in (None, "", "   ", "abcd"):
        assert _code(pr.check_rewrite_reason, "WORKSHOP_ERROR", note) == "REWRITE_NOTE_REQUIRED"
