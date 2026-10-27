from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from chatbot.adapters.outbound.documents import (
    GoogleDriveFolderDownloader,
    PdfDirectorySource,
    normalize_page_text,
)


def test_normalize_page_text_removes_layout_noise() -> None:
    raw = "Saúde men-\r\ntal  e\tcuidado\n\n\n\nSegundo parágrafo"

    assert normalize_page_text(raw) == "Saúde mental e cuidado\n\nSegundo parágrafo"


async def test_pdf_source_loads_files_in_order_and_ignores_empty_pages(tmp_path: Path) -> None:
    (tmp_path / "b.pdf").touch()
    (tmp_path / "a.pdf").touch()
    readers = [
        SimpleNamespace(
            pages=[
                SimpleNamespace(extract_text=lambda: " página A "),
                SimpleNamespace(extract_text=lambda: None),
            ]
        ),
        SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: "página B")]),
    ]

    with patch(
        "chatbot.adapters.outbound.documents.pdf.PdfReader",
        side_effect=readers,
    ):
        pages = await PdfDirectorySource(tmp_path).load()

    assert [(page.source, page.page, page.text) for page in pages] == [
        ("a.pdf", 1, "página A"),
        ("b.pdf", 1, "página B"),
    ]


async def test_pdf_source_rejects_missing_empty_or_unreadable_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="diretório"):
        await PdfDirectorySource(tmp_path / "missing").load()

    with pytest.raises(FileNotFoundError, match="nenhum PDF"):
        await PdfDirectorySource(tmp_path).load()

    (tmp_path / "empty.pdf").touch()
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: " ")])
    with (
        patch("chatbot.adapters.outbound.documents.pdf.PdfReader", return_value=reader),
        pytest.raises(ValueError, match="texto extraível"),
    ):
        await PdfDirectorySource(tmp_path).load()


def test_google_drive_downloader_validates_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Google Drive"):
        GoogleDriveFolderDownloader("https://example.com/folder", tmp_path)


async def test_google_drive_downloader_returns_only_pdfs(tmp_path: Path) -> None:
    downloaded = [str(tmp_path / "a.pdf"), str(tmp_path / "nota.txt")]
    downloader = GoogleDriveFolderDownloader(
        "https://drive.google.com/drive/folders/id",
        tmp_path,
    )

    with patch(
        "chatbot.adapters.outbound.documents.google_drive.gdown.download_folder",
        return_value=downloaded,
    ) as download_folder:
        paths = await downloader.download()

    assert paths == (tmp_path / "a.pdf",)
    download_folder.assert_called_once()


@pytest.mark.parametrize("downloaded", [None, ["nota.txt"]])
async def test_google_drive_downloader_rejects_invalid_result(
    tmp_path: Path,
    downloaded: list[str] | None,
) -> None:
    downloader = GoogleDriveFolderDownloader(
        "https://drive.google.com/drive/folders/id",
        tmp_path,
    )

    with (
        patch(
            "chatbot.adapters.outbound.documents.google_drive.gdown.download_folder",
            return_value=downloaded,
        ),
        pytest.raises(RuntimeError),
    ):
        await downloader.download()
