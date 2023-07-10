from datetime import datetime
from pathlib import PurePath
from typing import Optional

from colorama import Fore, Style
from httpx import AsyncClient
from lingua import Language

from entity_recognizer import Entity
from entity_recognizer.recognition_manager import find_entities_in_file
from .filters import filter_plaintext
from .metadata import get_file_format_magic, parse_mime_type, get_text_languages
from .ocr import run_ocr
from .tika import get_tika_metadata, get_tika_content


class File:
    def __init__(self, path: str):
        self.path_obj = PurePath(path)
        self.format = "unknown"
        self.plaintext = ""
        self.language: Optional[Language] = None
        self.author = "unknown"
        self.timestamp: Optional[datetime] = None
        self.entities: list[Entity] = []
        self.valid = False

    @property
    def path(self):
        return self.path_obj.__str__()

    @property
    def filename(self):
        return self.path_obj.name

    async def process(self, client: AsyncClient):
        metadata = await get_tika_metadata(self.path)

        mime_format = metadata.get("Content-Type", "")
        if not mime_format:
            # try to get file format from magic
            mime_format = get_file_format_magic(self.path)

        file_format = parse_mime_type(mime_format)
        if not file_format:
            print(f"{Fore.LIGHTMAGENTA_EX}{self}: unknown mime type: {mime_format}{Style.RESET_ALL}")
            return
        if file_format in ["zip"]:
            return

        # file is handled by ocr
        ocr_type = file_format in ["png", "jpg", "jpeg", "tiff"]
        if ocr_type:
            plaintext, language = await run_ocr(self.path)
        else:
            plaintext = await get_tika_content(self.path)
            langs = get_text_languages(plaintext)
            language = langs[0].language if langs else None

        if not plaintext:
            print(f"{Fore.LIGHTMAGENTA_EX}{self}: has no content{Style.RESET_ALL}")
            return

        if not language:
            print(f"{Fore.LIGHTMAGENTA_EX}{self}: couldn't determine language{Style.RESET_ALL}")
            return

        plaintext = filter_plaintext(file_format, plaintext, ocr_type)

        self.format = file_format
        self.plaintext = plaintext
        self.language = language
        self.timestamp = metadata.get("dcterms:created", datetime.now())
        self.author = metadata.get("dc:creator", "unknown")

        # file should be marked as valid because if something goes wrong during entity recognition
        # at least the metadata and plaintext will be saved
        self.valid = True

        try:
            entities = await find_entities_in_file(client, self)
        except Exception as e:
            print(f"{Fore.RED}{self}: Error while recognizing entities {e}{Style.RESET_ALL}")
            return

        self.entities = entities

    def make_document(self):
        return {
            "filename": self.filename,
            "path": self.path,
            "format": self.format,
            "plaintext": self.plaintext,
            "language": self.language.iso_code_639_1.name.lower(),
            "author": self.author,
            "timestamp": self.timestamp,
            "entities": {
                "name": "file",
            }
        }

    def __str__(self):
        return f"File({self.path})"

    def __repr__(self):
        return self.__str__()
