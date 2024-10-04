# Fansub-encoding-tools
Some useful scripts for encoders of fansub groups


## generate_cmp.py

#### Overview

`generate_cmp.py` is a Python script designed to compare frames from a raw video and an encoded video. It caches the frame types (I/B/P frames) for both videos, processes specific or random frames, and adds text annotations to the frames before saving them as images.

#### Dependencies

1. Python 3.x
2. Required Python libraries:
   - `opencv-python`
   - `av`
   - `concurrent.futures`

You can install the required libraries using `pip`:

```bash
pip install opencv-python av
```

#### Command-Line Usage

```bash
python generate_cmp_en.py raw.mkv encoded.mkv
```

Where:
- `raw.mkv`: The raw video file.
- `encoded.mkv`: The encoded video file to compare against the raw video.
- 
#### Interactive Mode

Once the script is running, it enters an interactive mode where you can input commands to process frames or configure the comparison.

**Commands:**

- **Frame number (e.g., `10`)**: Same as `encoded n`.
- **`raw n`**: Processes the frame number n (n is the frame number in raw video, and offset number will be applied when extracting encoded frame).
- **`encoded n`**: Processes the frame number n (n is the frame number in encoded video, and offset number will be applied when extracting raw frame).
- **`random n`**: Randomly selects `n` frames and processes them.
- **`set head n`**: Sets the first frame of the encoded video to correspond to frame `n` of the raw video.
- **`set tail n`**: Sets the last frame of the encoded video to correspond to frame `n` of the raw video.
- **`done`**: Exits the script.

#### Example Workflow

1. **Start the script:**

   ```bash
   python generate_cmp_en.py raw.mkv encoded.mkv
   ```

2. **Set a head or tail offset (optional):**

   ```bash
   set head 10
   ```

3. **Get a specific frame:**

   ```bash
   15
   raw 114514
   encoded 1919810
   ```

4. **Get random frames:**

   ```bash
   random 50
   ```

5. **Exit:**

   ```bash
   done
   ```

#### Output

Processed frames are saved as PNG files in the `output_frames` directory. The files include the frame number, its type (I, P, or B), and whether it is from the raw or encoded video.

---

## organize.sh

#### Overview

`organize_en.sh` is a Bash script designed to handle and organize MKV files within a folder structure. It performs the following tasks:
- Extracts video and audio tracks from the MKV file.
- Merges the video, audio, subtitles, chapters, and font attachments back into a new MKV file.
- 
Basicly, I use this script to produce collections when a season ends.

#### Prerequisites

Ensure the following tools are installed on your system:

1. **mkvextract**: Part of the MKVToolNix package, used to extract tracks from an MKV file.
2. **mkvmerge**: Also part of the MKVToolNix package, used to merge tracks and attachments into an MKV file.

Install them using your package manager:

- On Debian/Ubuntu:
  ```bash
  sudo apt install mkvtoolnix
  ```

- On macOS (with Homebrew):
  ```bash
  brew install mkvtoolnix
  ```


#### Script Workflow

The script processes multiple folders (in the format `E01`, `E02`, ..., `E12`) within the current directory. Each folder must contain:
- 1 `.mkv` file (the video).
- 2 `.ass` subtitle files (`chs_jpn` and `cht_jpn` for Simplified and Traditional Chinese subtitles).
- 1 `.txt` file (chapter information).
- 1 `subsetted_fonts` directory containing font files.


#### Folder Structure Example

Each folder (e.g., `E01`, `E02`, etc.) should have the following structure:

```
E01/
│
├── some_video.mkv
├── chs_jpn_subtitle.ass
├── cht_jpn_subtitle.ass
├── chapters.txt
└── subsetted_fonts/
    ├── some_font.ttf
    └── another_font.otf
```

#### Running the Script

1. **Navigate to the directory containing the `E01`, `E02`, ..., `E12` folders**:
   ```bash
   cd /path/to/your/directories
   ```

2. **Run the script**:
   ```bash
   bash organize.sh
   ```

The script will process each folder sequentially, ensuring that the required files exist and following these steps:
1. Extracts the video and audio from the `.mkv` file.
2. Attaches the subtitles, chapters, and fonts.
3. Merges everything into a new `.mkv` file and replaces the original.

#### Error Handling

The script will terminate with an error message if:
- Missing required files (e.g., the `.mkv`, `.ass`, `.txt`, or `subsetted_fonts` folder).
- A failure occurs while extracting or merging the MKV file.

Example error messages:
- **Missing subtitles**:
  ```bash
  Error: Folder E01 is missing required subtitle files.
  ```
- **Incorrect folder structure**:
  ```bash
  Error: The file structure in folder E01 is incorrect.
  ```

#### Output

Upon successful completion, each folder will contain an updated `.mkv` file, where the video, audio, subtitles, chapters, and fonts have been merged.
