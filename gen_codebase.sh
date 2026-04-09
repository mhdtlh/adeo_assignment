#!/bin/bash

OUTPUT="codebase_1.txt"
SCRIPT_NAME="gen_codebase.sh"

# Clear/Create the output file
> "$OUTPUT"

echo "Building Hierarchical Tree..."
echo "--- REPOSITORY STRUCTURE ---" >> "$OUTPUT"

# 1. TREE BLACKLIST: Hide messy data folders from the visual tree
IGNORE_TREE="(venv.*|\.git|__pycache__|node_modules|chroma_data|neo4j_data|hf_cache|source_docs|logs|\.idea|\.vscode)"

# 2. SPECIFIC FILES TO IGNORE: Add your target scripts here
IGNORE_FILES="($OUTPUT|$SCRIPT_NAME|generate_codebase.sh|ingestion_cache\.json|query_engine\.py|ingestion\.py)"

# Build the visual tree, ignoring specific folders and files
find . -maxdepth 4 -not -path '*/.*' 2>/dev/null | \
    grep -vE "$IGNORE_TREE" | \
    grep -vE "$IGNORE_FILES" | \
    sort | \
    sed -e "s/[^-][^\/]*\// |/g" -e "s/| /|- /g" >> "$OUTPUT"

echo -e "\n--- FILE CONTENTS ---\n" >> "$OUTPUT"
echo "Dumping Contents..."

# 3. FILE WHITELIST: ONLY dump actual code files (.py, .yml, Dockerfile, .sh)
find . -type f 2>/dev/null | \
    grep -vE "$IGNORE_TREE" | \
    grep -vE "$IGNORE_FILES" | \
    grep -E "(\.py|\.yml|\.yaml|Dockerfile|\.sh)$" | while read -r file; do
    
    echo "--- FILE: $file ---" >> "$OUTPUT"
    cat "$file" >> "$OUTPUT"
    echo -e "\n" >> "$OUTPUT"
done

echo "Done! Clean structure and pure code saved to $OUTPUT"