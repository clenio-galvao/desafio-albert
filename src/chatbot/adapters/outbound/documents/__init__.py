"""Aquisição e leitura da base documental."""

from chatbot.adapters.outbound.documents.catalog import resolve_document_title
from chatbot.adapters.outbound.documents.google_drive import GoogleDriveFolderDownloader
from chatbot.adapters.outbound.documents.pdf import PdfDirectorySource, normalize_page_text

__all__ = [
    "GoogleDriveFolderDownloader",
    "PdfDirectorySource",
    "normalize_page_text",
    "resolve_document_title",
]
