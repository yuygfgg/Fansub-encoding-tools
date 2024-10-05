# Fansub-encoding-tools

Some useful scripts for encoders of fansub groups

```
generate_cmp.py - An interactive comparism image generator, with frame number offset support.

organize.sh - A file organizor, useful when you have 12 (or even worse, 24) videos, each 2 subtitles and tens of subsetted fonts (hundereds in total) to deal with.

part_reencode.py - A video partial re-encoder. It re-encodes only part of the video using the specified vapoursynth script and encoder params, leaving other part untouched.
```

## generate_cmp.py

### Overview

`generate_cmp.py` is a Python script designed to compare frames from a raw video and an encoded video. It caches the frame types (I/B/P frames) for both videos, processes specific or random frames, and adds text annotations to the frames before saving them as images.

### Dependencies

1. Python 3.x
2. Required Python libraries:
   - `opencv-python`
   - `av`
   - `concurrent.futures`

You can install the required libraries using `pip`:

```bash
pip install opencv-python av
```

### Command-Line Usage

```bash
python generate_cmp.py raw.mkv encoded.mkv
```

Where:
- `raw.mkv`: The raw video file.
- `encoded.mkv`: The encoded video file to compare against the raw video.

### Interactive Mode

Once the script is running, it enters an interactive mode where you can input commands to process frames or configure the comparison.

**Commands:**

- **Frame number (e.g., `10`)**: Same as `encoded n`.
- **`raw n`**: Processes the frame number n (n is the frame number in raw video, and offset number will be applied when extracting encoded frame).
- **`encoded n`**: Processes the frame number n (n is the frame number in encoded video, and offset number will be applied when extracting raw frame).
- **`random n`**: Randomly selects `n` frames and processes them.
- **`set head n`**: Sets the first frame of the encoded video to correspond to frame `n` of the raw video.
- **`set tail n`**: Sets the last frame of the encoded video to correspond to frame `n` of the raw video.
- **`done`**: Exits the script.

### Example Workflow

1. **Start the script:**

   ```bash
   python generate_cmp.py raw.mkv encoded.mkv
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

### Output

Processed frames are saved as PNG files in the `output_frames` directory. The files include the frame number, its type (I, P, or B), and whether it is from the raw or encoded video.

---

## organize.sh

### Overview

`organize.sh` is a Bash script designed to handle and organize MKV files within a folder structure. It performs the following tasks:
- Extracts video and audio tracks from the MKV file.
- Merges the video, audio, subtitles, chapters, and font attachments back into a new MKV file.

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


### Script Workflow

The script processes multiple folders (in the format `E01`, `E02`, ..., `E12`) within the current directory. Each folder must contain:
- 1 `.mkv` file (the video).
- 2 `.ass` subtitle files (`chs_jpn` and `cht_jpn` for Simplified and Traditional Chinese subtitles).
- 1 `.txt` file (chapter information).
- 1 `subsetted_fonts` directory containing font files.


### Folder Structure Example

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

### Running the Script

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

### Error Handling

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

---

## part_reencode.py

Original by Kukoc@Magic-Raws https://skyeysnow.com/forum.php?mod=viewthread&tid=41638

### Overview

`part_reencode.py` is a Python script designed for partial re-encoding of close-gop HEVC/AVC video files(encoded with `no-open-gop`. The script’s core functionality involves **splitting**, **encoding**, and **merging** video segments specified by the user. It utilizes **VapourSynth** for video processing and **mkvmerge** for merging the re-encoded segments with the original video. This approach allows selective re-encoding of video parts without re-encoding the entire video, saving time and computational resources. Supported encoders include `x264` and `x265`.

### Functionality

This script performs the following operations:

1. **Splitting**: The video is split into specified segments.
2. **Encoding**: The segments are encoded using `x264` or `x265`.
3. **Merging**: The re-encoded segments are merged back with the original video, producing the final output file.

### Dependencies

Before running the script, ensure that the following tools and libraries are installed:

- **VapourSynth**: A video processing framework that supports scriptable video processing.
- **mkvmerge**: A tool used to merge video segments into Matroska (MKV) files.
- **ffprobe**: A tool for analyzing video frames to determine keyframe positions.
- **Python 3.x**: The script is written for Python 3.x.

Additionally, you will need the following Python libraries:

```bash
pip install vapoursynth xml.etree.ElementTree
```

### Usage

#### Basic Command

```bash
python part_reencode.py <input> <segments> <x26x_param> <vapoursynth_script> <output> [--encoder] [--qpfile] [--force_expand]
```

#### Arguments

- `input`: **Required**. The path to the input video file. Supported formats include `.hevc`, `.avc`, `.265`, `.264`.
- `segments`: **Required**. A string representation of the list of segments to process, e.g., `[[0, 100], [200, 300]]`, representing frame ranges.
- `x26x_param`: **Required**. Encoding parameters for `x264` or `x265` encoders. For example, `--y4m  --preset slow --crf 18`. **Note that `--y4m ` should always be added, or the script will crash or output garbage.**
- `vapoursynth_script`: **Required**. Path to the VapourSynth script used for video reencoding part. The script should output the save number of frames as the raw video.
- `output`: **Required**. The path to the output video file.
- `--encoder`: **Optional**. Specifies whether to use `x264` or `x265` for encoding. The default is `x265`.
- `--qpfile`: **Optional**. Path to a QP (Quantization Parameter) file, used to control quantization levels for specific frames.
- `--force_expand`: **Optional**. When enabled, the script forces the segment boundaries to expand to the nearest I-frame to ensure GOP (Group of Pictures) integrity.

#### Example Commands

1. Re-encode frames 0 to 100 and 200 to 300 of `sample.hevc` using `x265` with the encoding parameters `--y4m --preset slow --crf 18`, and use the VapourSynth script `script.vpy`. The output will be saved as `output.hevc`.

```bash
python part_reencode.py sample.hevc "[[0, 100], [200, 300]]" "--y4m --preset slow --crf 18" script.vpy output.hevc
```

2. Use the `x264` encoder and force the segments to expand to the nearest I-frame.

```bash
python part_reencode.py sample.avc "[[500, 1000]]" "--y4m --preset veryfast --crf 22" script.vpy output.avc --encoder x264 --force_expand
```

3. Use a QP file for encoding.

```bash
python part_reencode.py input.265 "[[0, 500], [1000, 1500]]" "--y4m --preset slow --crf 20" script.vpy output.265 --qpfile qpfile.txt
```

#### Detailed Functionality

##### 1. **Splitting and Keyframe Handling**

The script can split the input video into segments based on the frame ranges specified by the user. To ensure the integrity of the video’s GOP structure, it can expand the segment boundaries to the nearest I-frame when the `--force_expand` option is enabled. This is done using `ffprobe` to detect keyframes in the video.

##### 2. **Encoding**

The script uses VapourSynth to process video frames and pipes the frames to the encoder through `VSPipe`. Two encoders are supported:

- `x264`: Used for H.264 video encoding.
- `x265`: Used for H.265 video encoding.

The encoding parameters for the encoder are passed through the `x26x_param` argument, allowing fine-grained control over the encoding process (e.g., `--preset`, `--crf`, etc.).

If a QP file is provided, its contents are applied to the appropriate frames, allowing control over the quantization levels for individual frames.

##### 3. **Merging and Output**

The script uses `mkvmerge` to merge the re-encoded segments with the original video. For each segment, the script encodes the video and merges it back into the main file. Temporary files created during this process are automatically cleaned up after the final output is generated.

#### Important Notes

- **The script only works with close-gop videos**

- **`--y4m` should always be added into `x26x_param`**

- **Input File Format**: The script only supports `.hevc`, `.avc`, `.265`, and `.264` input files. If the input file is not in one of these formats, the script will raise an error.
  
- **Encoder Selection**: By default, the script uses `x265`. To use `x264`, you must specify `--encoder x264`.

- **Segment Expansion**: To ensure the GOP structure is intact, you can use the `--force_expand` option to expand the specified segments to the nearest I-frame. If this option is not enabled, the script will encode the exact frame ranges provided, but this may result in playback issues if the segments don’t align with I-frames.

- **QP Files**: QP files allow you to control the quantization levels on a per-frame basis, which can be useful for fine-tuning video quality. If you need to use a QP file, pass its path through the `--qpfile` argument.

### Workflow

1. **Input File Validation**: The script checks the input file format. If the format is invalid, the script raises a `ValueError`.
2. **Environment Setup**: Depending on the operating system (Windows or POSIX), appropriate system environment variables are set to ensure the encoder is available.
3. **Keyframe Handling**: If `--force_expand` is enabled, the script uses `ffprobe` to find keyframes and adjusts the segment boundaries accordingly.
4. **Segment Encoding**: For each segment, the script uses VapourSynth to process the video stream and pipes it into the encoder.
5. **Merging**: `mkvmerge` is used to merge the re-encoded segments with the original video, producing a final output file.
6. **Cleanup**: All temporary files created during the process are deleted to keep the working directory clean.

### Error Handling

- **Invalid Input File Format**: If the input file is not in a supported format, the script raises a `ValueError` and stops execution.
- **Invalid Segment Range**: If the provided segment frame ranges exceed the total number of frames in the input file, the script raises a `ValueError`.
