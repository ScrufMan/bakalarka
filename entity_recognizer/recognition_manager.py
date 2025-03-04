import asyncio
from asyncio import Semaphore
from typing import TYPE_CHECKING

from httpx import AsyncClient
from lingua import Language

from config import config
from entity_recognizer.post_processor import find_btc_adresses, find_bank_accounts
from utils import setup_logger, run_sync_fn_async_cpu
from utils.text import split_string
from . import Entity
from .nametag import run_nametag
from .spacy import run_spacy

# prevent cyclic import
if TYPE_CHECKING:
    from file_processor import File

logger = setup_logger(__name__)


async def process_batch(client: AsyncClient, plaintext: str, language: Language, is_tabular: bool) -> list[Entity]:
    if language in config.LANGUGAGE_TO_NAMETAG_MODEL:
        batch_entities = await run_nametag(client, plaintext, language, is_tabular)
    elif language in config.LANGUAGE_TO_SPACY_MODEL:
        batch_entities = await run_sync_fn_async_cpu(run_spacy, plaintext, language, is_tabular)
    else:
        raise NotImplementedError(f"Language {language} is not supported")

    batch_entities.extend(find_btc_adresses(plaintext))
    batch_entities.extend(find_bank_accounts(plaintext))
    return batch_entities


async def batch_with_semaphore(sem: Semaphore, client: AsyncClient, plaintext: str, language: Language,
                               is_tabular: bool):
    async with sem:  # Acquire semaphore
        return await process_batch(client, plaintext, language, is_tabular)


async def find_entities_in_file(client: AsyncClient, file: "File") -> list[Entity]:
    # Create a semaphore with a batch limit for this specific file
    batch_workers = config.BATCH_WORKERS
    sem = Semaphore(batch_workers)

    is_tabular = file.format in config.TABULAR_FORMATS

    plaintext = file.plaintext
    entities = []

    # split large texts into smaller batches
    if len(plaintext) > 500000:
        batches = split_string(plaintext, 500000)
        n_batches = len(batches)
        tasks = [batch_with_semaphore(sem, client, batch, file.language, is_tabular) for batch in batches]

        finished_tasks = 0
        for completed_task in asyncio.as_completed(tasks):
            batch_entities = await completed_task
            entities.extend(batch_entities)
            finished_tasks += 1
            logger.info(f"{file}: Finished batch {finished_tasks}/{n_batches}")
    else:
        entities = await process_batch(client, plaintext, file.language, is_tabular)

    return entities
