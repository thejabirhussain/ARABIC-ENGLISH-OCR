import pandas as pd
from pathlib import Path
from typing import List
import time
import logging
from .translator_model import TranslatorModel
from .normalizer import Normalizer

logger = logging.getLogger(__name__)

class TranslationService:
    """Service for translating extracted tables using batch processing"""
    
    def __init__(self, translator_model: TranslatorModel):
        self.translator = translator_model
        self.normalizer = Normalizer()
    
    def translate_tables(self, csv_files: List[str], output_dir: str) -> List[str]:
        """Translate all CSV files using efficient batch processing"""
        translated_files = []
        
        for csv_path in csv_files:
            csv_path = Path(csv_path)
            logger.info(f"Processing {csv_path.name}...")
            
            try:
                # Read CSV (no headers)
                try:
                    df = pd.read_csv(csv_path, header=None)
                except pd.errors.EmptyDataError:
                    logger.warning(f"Empty CSV: {csv_path}")
                    # Create empty translated file
                    output_path = Path(output_dir) / f"{csv_path.stem}_translated.csv"
                    with open(output_path, 'w') as f:
                        pass
                    translated_files.append(str(output_path))
                    continue

                # Translate using batch processing
                start_time = time.time()
                translated_df = self._process_dataframe(df)
                duration = time.time() - start_time
                
                # Save
                output_path = Path(output_dir) / f"{csv_path.stem}_translated.csv"
                translated_df.to_csv(output_path, index=False, header=False, encoding='utf-8-sig')
                translated_files.append(str(output_path))
                
                logger.info(f"✅ Translated {csv_path.name} in {duration:.2f}s")
                
            except Exception as e:
                logger.error(f"❌ Failed to translate {csv_path.name}: {e}")
                import traceback
                traceback.print_exc()
                # Create original file copy or empty as fallback?
                # For now continue, caller handles missing file or index mismatch
                continue
        
        return translated_files
    
    def _process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        OPTIMIZED batch processing pipeline:
        1. Normalize numerals/punctuation FIRST
        2. Collect UNIQUE Arabic text strings (skip pure numbers)
        3. Batch translate ALL at once
        4. Apply translation map back to DataFrame
        """
        
        # Step 1: Normalize entire DataFrame (convert Persian/Arabic numerals)
        logger.info("Step 1: Normalizing text...")
        
        def normalize_cell(x):
            if isinstance(x, str):
                return self.normalizer.clean_text(x)
            return x
        
        # Apply to all cells (this converts ۱۲۳ → 123)
        df_normalized = df.applymap(normalize_cell)
        
        # Step 2: Collect UNIQUE Arabic strings (skip numbers!)
        logger.info("Step 2: Collecting unique Arabic strings...")
        unique_strings = set()
        
        def collect_if_arabic(x):
            """Only collect cells with actual Arabic LETTERS (not just numbers)"""
            if isinstance(x, str) and x.strip():
                # Must have Arabic letters AND not be pure numeric
                if self.normalizer.has_arabic_letters(x) and not self.normalizer.is_numeric_only(x):
                    unique_strings.add(x)
        
        # Scan entire DataFrame
        df_normalized.applymap(collect_if_arabic)
        
        # Step 3: Batch translate all unique strings
        unique_list = list(unique_strings)
        logger.info(f"Step 3: Translating {len(unique_list)} unique Arabic strings...")
        
        if not unique_list:
            logger.warning("No Arabic text found to translate!")
            return df_normalized
        
        translated_list = self.translator.translate_batch(unique_list, batch_size=32)
        translation_map = dict(zip(unique_list, translated_list))
        
        # Debug: Show sample translations
        for i, (orig, trans) in enumerate(list(translation_map.items())[:5]):
            logger.debug(f"  '{orig}' → '{trans}'")
        
        # Step 4: Apply translation map to DataFrame
        logger.info("Step 4: Applying translations...")
        
        def apply_translation(x):
            if isinstance(x, str) and x in translation_map:
                return translation_map[x]
            return x
        
        df_translated = df_normalized.applymap(apply_translation)

        # Step 5: Apply Financial Glossary (Post-Processing)
        logger.info("Step 5: Applying Financial Glossary...")
        
        financial_glossary = {
            "Untraded liabilities": "Non-current liabilities",
            "Traded liabilities": "Current liabilities",
            "Untraded Assets": "Non-current assets",
            "Traded Assets": "Current assets",
            "Property Rights": "Equity",
            "Property rights": "Equity",
            "TotalProperty": "Total Equity",
            "Cash is like cash": "Cash and cash equivalents",
            "WantedTax": "Zakat Payable", 
            "Dion": "Loans",
            "Rasalmal": "Capital",
            "EarningsKeeping": "Retained Earnings",
            "Allocations": "Provisions",
            "LiabilitiesContracts": "Lease Liabilities",
            "Contracts Rents": "Lease Liabilities",
            "AccountsReceivable": "Trade Receivables",
            "AccountsPayable": "Trade Payables",
            "Inventory": "Inventories", 
            "Stocks": "Inventories",
            "Financing": "Funding",
            "Derivative Financial Instruments": "Derivative financial instruments",
            "Property rights related to Shareholders": "Equity attributable to shareholders",
            "InvestmentsFishratAssociateShare": "Investments in associates",
            "InvestmentsViaToolsDebt": "Investments in debt instruments",
            "Shorthagel Loans": "Short-term loans",
            "Zakat": "Zakat",
            "Toms Factory & Equipment": "Property, Plant and Equipment",
            "AssetsTommedMadinaAkhri": "Other Debit Assets",
            "AssetsTommedCityExtreme": "Other Assets",
            "InvestmentShortHall11": "Short-term investments",
            "NaybalreyesExecutive": "Vice Executive President", 
            "ReyesBoard": "Chairman of Board",
            "Dhammamedina Commercial": "Trade Receivables",
            "Dhamdaineh": "Trade Payables"
        }

        # Also handle partial matches or keys that might be slightly different in casing
        glossary_keys = list(financial_glossary.keys())

        def apply_glossary(x):
            if not isinstance(x, str):
                return x
            
            x_clean = x.strip()
            
            # Direct match
            if x_clean in financial_glossary:
                return financial_glossary[x_clean]
            
            # Case insensitive match
            for k in glossary_keys:
                if x_clean.lower() == k.lower():
                    return financial_glossary[k]
                # Partial match for some known phrases if exact match failed
                if k in x_clean and len(x_clean) < len(k) + 5: # Close match
                     return x_clean.replace(k, financial_glossary[k])

            return x

        df_translated = df_translated.applymap(apply_glossary)
        
        return df_translated
