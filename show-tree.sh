#!/usr/bin/env bash

show_tree() {
    local path="$1"
    local depth="$2"
    shift 2
    local exclude=("$@")

    local indent=""
    for ((i=0; i<depth; i++)); do
        indent+="    "
    done

    # Listar contenido ordenado
    for item in "$path"/* "$path"/.*; do
        [[ ! -e "$item" ]] && continue

        local name
        name="$(basename "$item")"

        # Ignorar . y ..
        [[ "$name" == "." || "$name" == ".." ]] && continue

        # Excluir carpetas/archivos
        for ex in "${exclude[@]}"; do
            [[ "$name" == "$ex" ]] && continue 2
        done

        if [[ -d "$item" ]]; then
            # Cyan
            echo -e "${indent}\e[36m+-- $name/\e[0m"
            show_tree "$item" $((depth + 1)) "${exclude[@]}"
        else
            # White
            echo -e "${indent}\e[37m+-- $name\e[0m"
        fi
    done
}

# ---- CONFIG ----
START_PATH="."
EXCLUDE_LIST=(".venv" "__pycache__" ".git" "others")

show_tree "$START_PATH" 0 "${EXCLUDE_LIST[@]}"
