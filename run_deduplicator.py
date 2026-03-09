from pathlib import Path
from icalarchive.storage import EventStore
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def deduplicate_all_sources(data_dir: str):
    store = EventStore(Path(data_dir))
    removed_total = 0
    
    logger.info("Starting retroactive deduplication on all existing sources...")
    
    # Iterate through all store files
    for store_file in store.store_dir.glob("*.ics"):
        source_name = store_file.stem
        logger.info(f"Processing source: {source_name}")
        
        try:
            removed = store.deduplicate_store(source_name)
            if removed > 0:
                logger.info(f" -> Removed {removed} duplicates from {source_name}")
                removed_total += removed
            else:
                logger.info(f" -> No duplicates found in {source_name}")
        except Exception as e:
            logger.error(f"Failed to deduplicate {source_name}: {e}")
            
    logger.info(f"Finished deduplication sweep. Total duplicates removed: {removed_total}")

if __name__ == '__main__':
    # Adjust this path if your application data is stored elsewhere
    deduplicate_all_sources('./data')
