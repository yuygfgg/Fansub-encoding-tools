#!/bin/bash

# Check if required tools are installed
if ! command -v mkvextract &> /dev/null; then
    echo "Error: mkvextract is not installed. Please install it and try again."
    exit 1
fi

if ! command -v mkvmerge &> /dev/null; then
    echo "Error: mkvmerge is not installed. Please install it and try again."
    exit 1
fi

# Define the list of folders to process
folders=$(find . -maxdepth 1 -type d -name 'E[0-9][0-9]')

if [ -z "$folders" ]; then
    echo "Error: No E01-E12 folders found in the current directory."
    exit 1
fi

# Iterate over each Exx folder
for dir in $folders; do
    echo "Checking folder $dir ..."

    # Check the number of files and folders
    mkv_count=$(find "$dir" -maxdepth 1 -type f -name '*.mkv' | wc -l)
    ass_count=$(find "$dir" -maxdepth 1 -type f -name '*.ass' | wc -l)
    txt_count=$(find "$dir" -maxdepth 1 -type f -name '*.txt' | wc -l)
    fonts_dir="$dir/subsetted_fonts"

    if [ ! -d "$fonts_dir" ]; then
        fonts_count=0
    else
        fonts_count=1
    fi

    if [ $mkv_count -ne 1 ] || [ $ass_count -ne 2 ] || [ $txt_count -ne 1 ] || [ $fonts_count -ne 1 ]; then
        echo "Error: The file structure in folder $dir is incorrect."
        exit 1
    fi

    # Get the filenames
    mkv_file=$(find "$dir" -maxdepth 1 -type f -name '*.mkv')
    txt_file=$(find "$dir" -maxdepth 1 -type f -name '*.txt')
    chs_ass=$(find "$dir" -maxdepth 1 -type f -name '*chs_jpn*.ass')
    cht_ass=$(find "$dir" -maxdepth 1 -type f -name '*cht_jpn*.ass')

    # Check if subtitle files exist
    if [ -z "$chs_ass" ] || [ -z "$cht_ass" ]; then
        echo "Error: Folder $dir is missing required subtitle files."
        exit 1
    fi

    # Extract video and audio streams
    echo "Processing folder $dir ..."

    # Create extraction directory
    extract_dir="$dir/extract_temp"
    mkdir -p "$extract_dir"

    # Extract video and audio tracks
    mkvextract tracks "$mkv_file" 0:"$extract_dir/video.hevc" 1:"$extract_dir/audio.aac"

    if [ $? -ne 0 ]; then
        echo "Error: Failed to extract video or audio."
        exit 1
    fi

    # Remove the original mkv file
    rm "$mkv_file"

    # Check for font files in the subsetted_fonts folder
    font_files=()
    while IFS= read -r -d '' font; do
        font_files+=("$font")
    done < <(find "$fonts_dir" -type f -print0)

    if [ ${#font_files[@]} -eq 0 ]; then
        echo "Error: No font files found in the subsetted_fonts folder of $dir."
        exit 1
    fi

    # Prepare attachment parameters
    attachments=()
    for font in "${font_files[@]}"; do
        # Set MIME type based on file extension
        extension="${font##*.}"
        case "$extension" in
            ttf)
                mime_type="font/ttf"
                ;;
            otf)
                mime_type="font/otf"
                ;;
            *)
                echo "Warning: Unrecognized font file type $font, skipping."
                continue
                ;;
        esac
        attachments+=(--attachment-mime-type "$mime_type" --attach-file "$font")
    done

    # Merge the new mkv file
    mkvmerge -o "$dir/new_$(basename "$mkv_file")" \
        --language 0:und "$extract_dir/video.hevc" \
        --language 0:ja "$extract_dir/audio.aac" \
        --language 0:zh-ch --track-name 0:"Chinese-Japanese Bilingual" --default-track 0:yes "$chs_ass" \
        --language 0:zh-tw --track-name 0:"Traditional Chinese-Japanese Bilingual" --default-track 0:no "$cht_ass" \
        --chapters "$txt_file" \
        "${attachments[@]}"

    if [ $? -ne 0 ]; then
        echo "Error: Failed to merge MKV file."
        exit 1
    fi

    # Remove extracted temporary files
    rm -r "$extract_dir"

    # Rename the new file to the original file name
    mv "$dir/new_$(basename "$mkv_file")" "$mkv_file"

    echo "Folder $dir processing completed."

done

echo "All operations completed."
