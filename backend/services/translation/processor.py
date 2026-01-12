# services/translation/processor.py
import pandas as pd
from pathlib import Path
import time
from .translator import ArabicTranslator


def translate_all_tables(csv_files: list, output_dir: str, translator: ArabicTranslator):
    """
    Translate all extracted CSV files (adapted from your batch processor)
    """
    translated_files = []
    success_count = 0
    fail_count = 0
    
    total_start_time = time.time()
    
    for file_path in csv_files:
        file_path = Path(file_path)
        output_filename = f"{file_path.stem}_translated.csv"
        output_path = Path(output_dir) / output_filename
        
        print(f"Processing {file_path.name}...")
        try:
            # Read CSV
            df = pd.read_csv(file_path)
            
            # Translate using your existing logic
            start_time = time.time()
            translated_df = process_dataframe(df, translator)
            duration = time.time() - start_time
            
            # Save translated file
            translated_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            
            print(f"✅ Saved to {output_filename} ({duration:.2f}s)")
            translated_files.append(output_path)
            success_count += 1
            
        except Exception as e:
            print(f"❌ Failed to process {file_path.name}: {e}")
            fail_count += 1
    
    total_duration = time.time() - total_start_time
    print(f"\nTranslation complete in {total_duration:.2f}s.")
    print(f"Success: {success_count}, Failed: {fail_count}")
    
    return translated_files


def process_dataframe(df: pd.DataFrame, translator: ArabicTranslator) -> pd.DataFrame:
    """
    Process a single DataFrame (your existing translation logic)
    Handles MultiIndex columns and mixed Arabic/numeric content
    """
    # Create a copy to avoid modifying original
    result_df = df.copy()
    
    # Handle MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        # Translate each level of MultiIndex
        new_columns = []
        for level_values in df.columns.levels:
            translated_level = []
            for val in level_values:
                if pd.notna(val) and isinstance(val, str):
                    translated = translator.translate(val)
                    translated_level.append(translated)
                else:
                    translated_level.append(val)
            new_columns.append(translated_level)
        
        # Reconstruct MultiIndex with translated values
        result_df.columns = pd.MultiIndex.from_tuples(
            [(new_columns[i][df.columns.codes[i][j]] 
              for i in range(len(df.columns.levels))) 
             for j in range(len(df.columns))],
            names=[translator.translate(str(name)) if name else name 
                   for name in df.columns.names]
        )
    else:
        # Translate regular columns
        result_df.columns = [
            translator.translate(str(col)) if isinstance(col, str) else col
            for col in df.columns
        ]
    
    # Translate index
    if df.index.name:
        result_df.index.name = translator.translate(str(df.index.name))
    
    result_df.index = [
        translator.translate(str(idx)) if isinstance(idx, str) else idx
        for idx in df.index
    ]
    
    # Translate cell values (only text, preserve numbers)
    for col in result_df.columns:
        result_df[col] = result_df[col].apply(
            lambda x: translator.translate(str(x)) 
            if pd.notna(x) and isinstance(x, str) and not is_numeric_string(x)
            else x
        )
    
    return result_df


def is_numeric_string(s: str) -> bool:
    """Check if string contains only numbers, commas, dots, and Arabic-Indic digits"""
    if not isinstance(s, str):
        return False
    
    # Remove common numeric characters
    cleaned = s.replace(',', '').replace('.', '').replace('%', '').strip()
    
    # Check if remaining is digits (Arabic or Western)
    arabic_indic = '٠١٢٣٤٥٦٧٨٩'
    return all(c.isdigit() or c in arabic_indic for c in cleaned)
