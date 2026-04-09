#!/usr/bin/env bash
# Backdate commits: each file gets its own commit starting from Dec 1, 2025
# Dates increment by 1 day per commit

set -euo pipefail

REPO_DIR="/home/arjavjain5203/Coding/AI_Native_Custom_Distro"
cd "$REPO_DIR"

# Starting date: December 1, 2025
START_DATE="2025-12-01"
DAY_OFFSET=0

# Collect all modified (tracked) files, excluding Aicustom/ binaries
MODIFIED_FILES=()
while IFS= read -r line; do
    status="${line:0:2}"
    file="${line:3}"
    # Skip Aicustom directory (large VM files)
    [[ "$file" == Aicustom/* ]] && continue
    MODIFIED_FILES+=("$file")
done < <(git status --short | grep "^ M ")

# Collect all untracked files, expanding directories, excluding __pycache__ and Aicustom/
UNTRACKED_FILES=()
while IFS= read -r line; do
    file="${line:3}"
    # Skip Aicustom directory
    [[ "$file" == Aicustom/* ]] && continue
    if [ -d "$file" ]; then
        while IFS= read -r f; do
            # Skip __pycache__ files
            [[ "$f" == *__pycache__* ]] && continue
            UNTRACKED_FILES+=("$f")
        done < <(find "$file" -type f)
    else
        # Skip __pycache__ files
        [[ "$file" == *__pycache__* ]] && continue
        UNTRACKED_FILES+=("$file")
    fi
done < <(git status --short | grep "^?? ")

# Combine all files: modified first, then untracked
ALL_FILES=("${MODIFIED_FILES[@]}" "${UNTRACKED_FILES[@]}")

TOTAL=${#ALL_FILES[@]}
echo "=== Backdating $TOTAL files starting from $START_DATE ==="
echo ""

for file in "${ALL_FILES[@]}"; do
    # Calculate the commit date
    COMMIT_DATE=$(date -d "$START_DATE + $DAY_OFFSET days" "+%Y-%m-%dT12:00:00")
    DAY_OFFSET=$((DAY_OFFSET + 1))

    # Get just the basename for the commit message
    BASENAME=$(basename "$file")

    echo "[$DAY_OFFSET/$TOTAL] Committing: $file  (date: $COMMIT_DATE)"

    # Stage the file
    git add "$file"

    # Commit with backdated author and committer dates
    GIT_AUTHOR_DATE="$COMMIT_DATE" \
    GIT_COMMITTER_DATE="$COMMIT_DATE" \
    git commit -m "Add $BASENAME" --quiet

done

echo ""
echo "=== Done! $TOTAL files committed from $START_DATE to $(date -d "$START_DATE + $((DAY_OFFSET - 1)) days" "+%Y-%m-%d") ==="
echo ""
echo "To verify: git log --oneline --format='%ad %s' --date=short | head -$TOTAL"
