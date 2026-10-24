"""画面の誤りの文の書き方：何が合わないかを書き、「正しくありません」とは書かない。"""

from pydantic import BaseModel, ValidationError

from app.web.rendering import error_text


class _Form(BaseModel):
    patient_id: str


def test_validation_error_names_what_to_check_and_does_not_say_incorrect() -> None:
    try:
        _Form.model_validate({})
    except ValidationError as exc:
        text = error_text(exc)
    else:  # pragma: no cover
        raise AssertionError("ValidationError が出るはず")
    assert text.startswith("入力を受け付けられません。次の項目を確かめてください：")
    # 何が合わないか（項目の名前と原因）を添え、「正しくありません」とは書かない
    assert "patient_id: Field required" in text
    assert "正しくありません" not in text
