from __future__ import annotations


def test_core_public_api_exports_main_classes() -> None:
    from app.core import DICOMBuilder, PixelGenerator, UIDGenerator

    assert DICOMBuilder is not None
    assert UIDGenerator is not None
    assert PixelGenerator is not None
