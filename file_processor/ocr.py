from typing import Optional

import cv2
import easyocr
import numpy as np
from lingua import Language
from pytesseract import pytesseract

from config import config
from file_processor.image_preprocessor import preprocess_ocr
from file_processor.metadata import determine_text_language
from utils import filter_for_lang_detection, setup_logger, run_sync_fn_async_cpu, generic_filter
from .tika_client import call_tika_ocr

logger = setup_logger(__name__)

available_easyocr_languages = ["abq",
                               "ady",
                               "af",
                               "ang",
                               "ar",
                               "as",
                               "ava",
                               "az",
                               "be",
                               "bg",
                               "bh",
                               "bho",
                               "bn",
                               "bs",
                               "ch_sim",
                               "ch_tra",
                               "che",
                               "cs",
                               "cy",
                               "da",
                               "dar",
                               "de",
                               "en",
                               "es",
                               "et",
                               "fa",
                               "fr",
                               "ga",
                               "gom",
                               "hi",
                               "hr",
                               "hu",
                               "id",
                               "inh",
                               "is",
                               "it",
                               "ja",
                               "kbd",
                               "kn",
                               "ko",
                               "ku",
                               "la",
                               "lez",
                               "lt",
                               "lv",
                               "mah",
                               "mai",
                               "mi",
                               "mn",
                               "mr",
                               "ms",
                               "mt",
                               "ne",
                               "new",
                               "nl",
                               "no",
                               "oc",
                               "pi",
                               "pl",
                               "pt",
                               "ro",
                               "ru",
                               "rs_cyrillic",
                               "rs_latin",
                               "sck",
                               "sk",
                               "sl",
                               "sq",
                               "sv",
                               "sw",
                               "ta",
                               "tab",
                               "te",
                               "th",
                               "tjk",
                               "tl",
                               "tr",
                               "ug",
                               "uk",
                               "ur",
                               "vi",
                               "uz"]


async def run_tesseract(preprocessed_image):
    text = await run_sync_fn_async_cpu(pytesseract.image_to_string, preprocessed_image, config=config.TESSERACT_CONFIG,
                                       lang=config.TESSERACT_LANG_STRING)
    text = generic_filter(text)
    text = text.lower()
    filtered_text = filter_for_lang_detection(text)
    return text, filtered_text


def run_easyocr(preprocessed_image, detected_lang: Language | None):
    if (detected_lang and detected_lang in config.SUPPORTED_LANGUAGES and
            detected_lang.iso_code_639_1.name.lower() in available_easyocr_languages):
        easyocr_langs = [detected_lang.iso_code_639_1.name.lower()]
        # add english because it's often used in combination with other languages
        if "en" not in easyocr_langs:
            easyocr_langs.append("en")
    else:
        easyocr_langs = config.EASYOCR_DEFAULT_LANGS
    reader = easyocr.Reader(easyocr_langs, gpu=config.GPU, model_storage_directory=config.EASYOCR_MODELS_DIR,
                            download_enabled=False)
    data = reader.readtext(preprocessed_image, detail=0)
    text = " ".join(data)
    text = generic_filter(text)
    text = text.lower()
    filtered_text = filter_for_lang_detection(text)

    return text, filtered_text


def determine_better_model(tess_prob: float, easyocr_prob: float) -> str | None:
    """
    Determine which model yields better language probability, therefore which model has better results
    """

    # if model confidence is smaller than 0.6, we don't trust it
    if max(tess_prob, easyocr_prob) < 0.6:
        return None

    #  try easyocr first, since it has better results
    if easyocr_prob >= 0.95:
        return "easyocr"
    if tess_prob == 1:
        return "tesseract"

    return "easyocr" if easyocr_prob > tess_prob else "tesseract"


def tika_ocr(file_path: str) -> tuple[Optional[str], Optional[Language]]:
    response = call_tika_ocr(file_path)
    text = response["content"] or ""
    text = generic_filter(text)
    text = text.lower()
    filtered_text = filter_for_lang_detection(text)
    lang, _ = determine_text_language(filtered_text)

    if not lang or lang not in config.SUPPORTED_LANGUAGES:
        return None, None
    return text, lang


def run_ocr(file_path: str) -> tuple[Optional[str], Optional[Language]]:
    """
    Perform OCR on the given file and return the text and language.
    """
    try:
        # handle images with non ascii paths
        image = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        logger.info(f"File({file_path}): Running Tessaract preprocessing")
        # preprocess the image and detect orientation with tesseract ocr
        image_preprocessed, tesseract_text, tesseract_lang, tesseract_prob = preprocess_ocr(image)

        logger.info(f"File({file_path}): Running EasyOCR")

        try:
            easyocr_text, easyocr_filtered = run_easyocr(image_preprocessed, tesseract_lang)
        except Exception as e:
            logger.error(f"File({file_path}): EasyOCR failed with exception: {e}")
            easyocr_text = ""
            easyocr_filtered = ""

        easyocr_lang, easyocr_prob = determine_text_language(easyocr_filtered)
        if not easyocr_lang or easyocr_lang not in config.SUPPORTED_LANGUAGES:
            easyocr_lang = None
            easyocr_prob = 0

        better_model = determine_better_model(tesseract_prob, easyocr_prob)
        if not better_model:
            # all models failed to obtained meaningful text
            logger.warning(f"File({file_path}): OCR failed to obtain meaningful text using Tika as fallback")
            return tika_ocr(file_path)

        text = easyocr_text if better_model == "easyocr" else tesseract_text
        lang = easyocr_lang if better_model == "easyocr" else tesseract_lang
        return text, lang

    except Exception as e:
        logger.error(f"File({file_path}): OCR failed with exception: {e}")
        return None, None
