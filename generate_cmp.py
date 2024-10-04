import cv2
import sys
import random
import os
import av
import concurrent.futures

# Initialize offsets
head_offset = 0  # head offset
tail_offset = 0  # tail offset

def cache_frame_types_av(video_path):
    """
    Cache all frame types (I/B/P) in the video using PyAV.
    """
    try:
        print(f"Caching frame types for {video_path}...")
        container = av.open(video_path)
        frame_types = []
        for frame in container.decode(video=0):
            pict_type = frame.pict_type.name  # 'I', 'P', 'B', etc.
            if pict_type in ['I', 'P', 'B']:
                frame_types.append(pict_type)
        print(f"Cached {len(frame_types)} frame types.")
        return frame_types
    except Exception as e:
        print(f"Error caching frame types: {e}")
        return []

def cache_frame_types_parallel(video_paths):
    """
    Cache frame types for multiple video files in parallel.
    """
    frame_types_dict = {}
    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_video = {executor.submit(cache_frame_types_av, vp): vp for vp in video_paths}
        for future in concurrent.futures.as_completed(future_to_video):
            video = future_to_video[future]
            try:
                frame_types = future.result()
                frame_types_dict[video] = frame_types
            except Exception as e:
                print(f"Failed to process video {video}: {e}")
                frame_types_dict[video] = []
    return frame_types_dict

def get_frame_type(cached_frame_types, frame_number):
    """
    Get the type of a specific frame from the cache.
    """
    if frame_number < len(cached_frame_types):
        return cached_frame_types[frame_number]
    return "Unknown"

def get_frame(video_path, frame_number):
    """
    Retrieve a specific frame from a video.
    """
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None

def draw_text_on_frame(frame, text):
    """
    Draw text information on the top-left corner of a frame.
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1
    thickness = 2
    color = (255, 255, 255)
    shadow_color = (0, 0, 0)

    # Calculate text size
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]

    # Text position
    text_x = 10
    text_y = 30

    # Draw shadow
    cv2.putText(frame, text, (text_x + 2, text_y + 2), font, font_scale, shadow_color, thickness + 1, cv2.LINE_AA)

    # Draw main text
    cv2.putText(frame, text, (text_x, text_y), font, font_scale, color, thickness, cv2.LINE_AA)

def process_frame(raw_video, encoded_video, frame_number, raw_frame_types, encoded_frame_types, output_dir, total_frames, raw_input=False):
    """
    Process a specific frame, extract and save the frame with information.

    raw_input: If True, the input is a raw video frame number; otherwise, it's an encoded video frame number.
    """
    if raw_input:
        # If the input is a raw video frame number, use the raw frame number and map it to the encoded video frame number
        raw_frame_number = frame_number
        encoded_frame_number = map_frame_number_from_raw(raw_frame_number, total_frames)
    else:
        # If the input is an encoded video frame number, use the encoded frame number and map it to the raw video frame number
        encoded_frame_number = frame_number
        raw_frame_number = map_frame_number_from_encoded(encoded_frame_number, total_frames)

    raw_frame = get_frame(raw_video, raw_frame_number)
    encoded_frame = get_frame(encoded_video, encoded_frame_number)

    if raw_frame is None or encoded_frame is None:
        print(f"Frame {raw_frame_number} or encoded frame {encoded_frame_number} does not exist in one of the videos.")
        return

    raw_frame_type = get_frame_type(raw_frame_types, raw_frame_number)
    encoded_frame_type = get_frame_type(encoded_frame_types, encoded_frame_number)

    # Save raw frame
    raw_output_path = os.path.join(output_dir, f"{frame_number}_raw.png")
    draw_text_on_frame(raw_frame, f"Raw, Frame {raw_frame_number}, Type: {raw_frame_type}")
    cv2.imwrite(raw_output_path, raw_frame)
    print(f"Saved {raw_output_path}")

    # Save encoded frame
    encoded_output_path = os.path.join(output_dir, f"{frame_number}_encoded.png")

    # Correct watermark display: the encoded frame number and raw video frame number should be properly mapped
    if raw_input:
        # If the input is a raw video frame number, display the mapped encoded frame number
        draw_text_on_frame(encoded_frame, f"Encoded, Frame {encoded_frame_number}, Type: {encoded_frame_type} (Original Frame {raw_frame_number})")
    else:
        # If the input is an encoded video frame number, display the mapped raw video frame number
        draw_text_on_frame(encoded_frame, f"Encoded, Frame {frame_number}, Type: {encoded_frame_type} (Original Frame {raw_frame_number})")

    cv2.imwrite(encoded_output_path, encoded_frame)
    print(f"Saved {encoded_output_path}")

def map_frame_number_from_encoded(encoded_frame_number, total_frames):
    """
    Map encoded video frame number to raw video frame number based on head or tail offset.
    """
    global head_offset, tail_offset

    if head_offset > 0 and tail_offset > 0:
        # If both head and tail are set, calculate the mapping range
        num_encoded_frames = total_frames - tail_offset + head_offset
        if num_encoded_frames <= 0:
            print("Error: head and tail offsets result in no valid frame range.")
            return encoded_frame_number  # Return the original frame number by default
        # Map within the encoded video frame range
        return head_offset + encoded_frame_number - 1
    elif head_offset > 0:
        # Only head offset is set
        return encoded_frame_number + head_offset - 1
    elif tail_offset > 0:
        # Only tail offset is set
        return total_frames - tail_offset + encoded_frame_number
    else:
        # No offset set, align directly
        return encoded_frame_number

def map_frame_number_from_raw(raw_frame_number, total_frames):
    """
    Map raw video frame number to encoded video frame number based on head or tail offset.
    """
    global head_offset, tail_offset

    if head_offset > 0 and tail_offset > 0:
        # If both head and tail are set, calculate the mapping range
        num_encoded_frames = total_frames - tail_offset + head_offset
        if num_encoded_frames <= 0:
            print("Error: head and tail offsets result in no valid frame range.")
            return raw_frame_number  # Return the original frame number by default
        # Map within the encoded video frame range
        return raw_frame_number - head_offset + 1
    elif head_offset > 0:
        # Only head offset is set
        return raw_frame_number - head_offset + 1
    elif tail_offset > 0:
        # Only tail offset is set
        return raw_frame_number - total_frames + tail_offset
    else:
        # No offset set, align directly
        return raw_frame_number

def main():
    global head_offset, tail_offset

    if len(sys.argv) != 3:
        print("Usage: python generate_cmp_en.py raw.mkv encoded.mkv")
        sys.exit(1)

    raw_video = sys.argv[1]
    encoded_video = sys.argv[2]
    output_dir = "output_frames"
    os.makedirs(output_dir, exist_ok=True)

    # Cache frame types in parallel
    video_paths = [raw_video, encoded_video]
    frame_types_dict = cache_frame_types_parallel(video_paths)
    raw_frame_types = frame_types_dict.get(raw_video, [])
    encoded_frame_types = frame_types_dict.get(encoded_video, [])

    # Get total number of frames in the video
    cap = cv2.VideoCapture(raw_video)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    print(f"Total number of frames in the video: {total_frames}")

    while True:
        user_input = input("Enter frame number, 'random n' for random frames, 'set (head/tail) n' to set offset, or type 'done' to exit: ")

        if user_input == "done":
            print("Exiting...")
            break
        elif user_input.startswith("set"):
            try:
                parts = user_input.split()
                if len(parts) != 3:
                    raise ValueError("Invalid set command format")

                option, value = parts[1], int(parts[2])
                if option == "head":
                    head_offset = value
                    print(f"Set the first frame of the encoded video to correspond to frame {head_offset} of the raw video")
                elif option == "tail":
                    tail_offset = value
                    print(f"Set the last frame of the encoded video to correspond to frame {tail_offset} of the raw video")
                else:
                    print("Invalid option. Use 'set head n' or 'set tail n'")
            except ValueError as e:
                print(f"Error setting offset: {e}")
        elif user_input.startswith("random"):
            try:
                n = int(user_input.split()[1])
                if n > total_frames:
                    print(f"n cannot exceed the total number of frames {total_frames}")
                    continue
                random_frames = random.sample(range(total_frames), n)
                # Process random frames in parallel using a thread pool
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = [executor.submit(process_frame, raw_video, encoded_video, fn, raw_frame_types, encoded_frame_types, output_dir, total_frames) for fn in random_frames]
                    for future in concurrent.futures.as_completed(futures):
                        pass  # Information is printed in process_frame
            except (ValueError, IndexError):
                print("Invalid random input. Usage: random n")
        else:
            try:
                # Interpret user input
                if user_input.startswith("raw "):
                    frame_number = int(user_input.split()[1])
                    if frame_number >= 0 and frame_number < total_frames:
                        process_frame(raw_video, encoded_video, frame_number, raw_frame_types, encoded_frame_types, output_dir, total_frames, raw_input=True)
                    else:
                        print(f"Frame number should be between 0 and {total_frames - 1}")
                elif user_input.startswith("encoded "):
                    frame_number = int(user_input.split()[1])
                    if frame_number >= 0 and frame_number < total_frames:
                        process_frame(raw_video, encoded_video, frame_number, raw_frame_types, encoded_frame_types, output_dir, total_frames, raw_input=False)
                    else:
                        print(f"Frame number should be between 0 and {total_frames - 1}")
                else:
                    # Interpret directly entered frame number as an encoded video frame number
                    frame_number = int(user_input)
                    if frame_number >= 0 and frame_number < total_frames:
                        process_frame(raw_video, encoded_video, frame_number, raw_frame_types, encoded_frame_types, output_dir, total_frames, raw_input=False)
                    else:
                        print(f"Frame number should be between 0 and {total_frames - 1}")
            except ValueError:
                print("Invalid frame number. Please enter a valid number or use 'raw n' or 'encoded n' to specify the frame.")

if __name__ == "__main__":
    main()
