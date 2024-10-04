# Fansub-encoding-tools
Some useful scripts for encoders of fansub groups


### generate_cmp.py

#### Overview

`generate_cmp_en.py` is a Python script designed to compare frames from a raw video and an encoded video. It caches the frame types (I/B/P frames) for both videos, processes specific or random frames, and adds text annotations to the frames before saving them as images.

---

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

---

#### Command-Line Usage

```bash
python generate_cmp_en.py raw.mkv encoded.mkv
```

Where:
- `raw.mkv`: The raw video file.
- `encoded.mkv`: The encoded video file to compare against the raw video.

---

#### Interactive Mode

Once the script is running, it enters an interactive mode where you can input commands to process frames or configure the comparison.

**Commands:**

- **Frame number (e.g., `10`)**: Displays and processes the specified frame from the encoded video.
- **`raw n`**: Processes the frame from the raw video corresponding to frame number `n`.
- **`encoded n`**: Processes the frame from the encoded video corresponding to frame number `n`.
- **`random n`**: Randomly selects `n` frames and processes them.
- **`set head n`**: Sets the first frame of the encoded video to correspond to frame `n` of the raw video.
- **`set tail n`**: Sets the last frame of the encoded video to correspond to frame `n` of the raw video.
- **`done`**: Exits the script.

---

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

---

#### Output

Processed frames are saved as PNG files in the `output_frames` directory. The files include the frame number, its type (I, P, or B), and whether it is from the raw or encoded video.
