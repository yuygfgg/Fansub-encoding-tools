# Original by Kukoc@Magic-Raws https://skyeysnow.com/forum.php?mod=viewthread&tid=41638
import argparse
import os
import sys

def SEM(
    fp_vc_input: str,
    segment_list: list,
    x26x_param: str,
    fp_vpy: str,
    fp_vc_output: str,
    fp_qpfile: str = None,
    encoder: str = "x265",
    force_expand: bool = True
):
    """
    Split, Encode then Merge for closed GOP hevc or avc file.
    """
    from vapoursynth import core

    valid_exts = ['.hevc', '.avc', '.265', '.264']
    ext = os.path.splitext(fp_vc_input)[1]
    if ext not in valid_exts:
        raise ValueError(f'Input file invalid.')

    print(f"Input file: {fp_vc_input}")
    print(f"Segment list: {segment_list}")
    print(f"Encoder: {encoder}")
    print(f"x26x parameters: {x26x_param}")
    print(f"VapourSynth script: {fp_vpy}")
    print(f"Output file: {fp_vc_output}")
    print(f"QPFile: {fp_qpfile if fp_qpfile else 'None'}")
    print(f"Force expand: {force_expand}")

    if os.name == 'nt':  # Windows
        path_var = 'Path'
        path_separator = '\\'
    else:  # POSIX
        path_var = 'PATH'
        path_separator = '/'

    if path_var in os.environ:
        os.environ[path_var] = os.environ[path_var] + ":" + sys.prefix + path_separator + "x26x" + ":" + sys.prefix
    else:
        os.environ[path_var] = sys.prefix + path_separator + "x26x" + ":" + sys.prefix

    if force_expand:
        iframe_segment_list = expand_segment_to_iframe(fp_vc_input, segment_list)
    else:
        iframe_segment_list = segment_list

    iframe_segment_list = sort_segment(iframe_segment_list)

    qp = None
    if fp_qpfile:
        with open(fp_qpfile, "r") as f:
            qpstr = f.readlines()
        qpstr = [i for i in qpstr if i != "\n"]
        qpstr = [i if i.endswith("\n") else i + "\n" for i in qpstr]
        qpstr = [i[:-3] for i in qpstr]
        qp = [int(i) for i in qpstr]

    file = '_tomerge.mkv'

    print(f"Running mkvmerge: mkvmerge -o \"{file}\" \"{fp_vc_input}\"")
    os.system(f'mkvmerge -o "{file}" "{fp_vc_input}"')

    qp_idx = 0
    last_Iframe = 0
    for seg in iframe_segment_list:
        Iframe1, Iframe2 = seg[0], seg[1]
        tmp_qp = []
        if qp:
            while qp_idx < len(qp):
                Qx = qp[qp_idx]
                if Qx < Iframe1:
                    qp_idx += 1
                elif Iframe1 <= Qx < Iframe2:
                    tmp_qp += [Qx - Iframe1]
                    qp_idx += 1
                else:
                    break
            tmp_qp_str = "\n".join([f"{i} K" for i in tmp_qp])
            with open("tmp_qp.qpfile", "w") as f:
                f.write(tmp_qp_str)

        # set file ext base on encoder type
        ext = ".265" if encoder == "x265" else ".264"

        encoder_command = f'{encoder} {x26x_param}'
        print(f"Using encoder command: {encoder_command}")
        print(f"Processing segment: {Iframe1}-{Iframe2}")

        if Iframe1 == 0:
            if qp:
                command = f'VSPipe "{fp_vpy}" -c y4m -s {Iframe1} -e {Iframe2 - 1} - | {encoder_command} --qpfile "tmp_qp.qpfile" -o "_newseg{ext}" -'
            else:
                command = f'VSPipe "{fp_vpy}" -c y4m -s {Iframe1} -e {Iframe2 - 1} - | {encoder_command} -o "_newseg{ext}" -'

            print(f"Running command: {command}")
            os.system(command)

            print(f"Running mkvmerge for first segment: mkvmerge -o \"_lastseg.mkv\" \"_newseg{ext}\"")
            os.system(f'mkvmerge -o "_lastseg.mkv" "_newseg{ext}"')
        else:
            if os.path.exists("_lastseg.mkv"):
                print(f"Running mkvmerge for segment: mkvmerge -o \"_newseg.mkv\" --split parts-frames:{last_Iframe+1}-{Iframe1+1} \"{file}\"")
                os.system(f'mkvmerge -o "_newseg.mkv" --split parts-frames:{last_Iframe+1}-{Iframe1+1} "{file}"')
                print(f"Merging last segment: mkvmerge -o \"_last.mkv\" \"_lastseg.mkv\" + \"_newseg.mkv\"")
                os.system(f'mkvmerge -o "_last.mkv" "_lastseg.mkv" + "_newseg.mkv"')
            else:
                print(f"Running mkvmerge for split: mkvmerge -o \"_last.mkv\" --split parts-frames:{last_Iframe+1}-{Iframe1+1} \"{file}\"")
                os.system(f'mkvmerge -o "_last.mkv" --split parts-frames:{last_Iframe+1}-{Iframe1+1} "{file}"')

            if qp:
                command = f'VSPipe "{fp_vpy}" -c y4m -s {Iframe1} -e {Iframe2 - 1} - | {encoder_command} --qpfile "tmp_qp.qpfile" -o "_newseg{ext}" -'
            else:
                command = f'VSPipe "{fp_vpy}" -c y4m -s {Iframe1} -e {Iframe2 - 1} - | {encoder_command} -o "_newseg{ext}" -'

            print(f"Running command: {command}")
            os.system(command)

            print(f"Running mkvmerge for new segment: mkvmerge -o \"_newseg.mkv\" \"_newseg{ext}\"")
            os.system(f'mkvmerge -o "_newseg.mkv" "_newseg{ext}"')

            print(f"Merging segments: mkvmerge -o \"_lastseg.mkv\" \"_last.mkv\" + \"_newseg.mkv\"")
            os.system(f'mkvmerge -o "_lastseg.mkv" "_last.mkv" + "_newseg.mkv"')

        last_Iframe = Iframe2

    if last_Iframe != core.lsmas.LWLibavSource(file).num_frames:
        print(f"Final mkvmerge for remaining frames: mkvmerge -o \"_newseg.mkv\" --split parts-frames:{last_Iframe+1}- \"{file}\"")
        os.system(f'mkvmerge -o "_newseg.mkv" --split parts-frames:{last_Iframe+1}- "{file}"')
        print(f"Merging final segments: mkvmerge -o \"_last.mkv\" \"_lastseg.mkv\" + \"_newseg.mkv\"")
        os.system(f'mkvmerge -o "_last.mkv" "_lastseg.mkv" + "_newseg.mkv"')
        print(f"Extracting final output: mkvextract \"_last.mkv\" tracks 0:\"{fp_vc_output}\"")
        os.system(f'mkvextract "_last.mkv" tracks 0:"{fp_vc_output}"')
    else:
        print(f"Extracting final output (no remaining frames): mkvextract \"_lastseg.mkv\" tracks 0:\"{fp_vc_output}\"")
        os.system(f'mkvextract "_lastseg.mkv" tracks 0:"{fp_vc_output}"')

    print(f"Cleaning up temporary files...")
    os.remove(file)
    if qp:
        os.remove("tmp_qp.qpfile")
    os.remove(f"_newseg{ext}")
    os.remove("_lastseg.mkv")
    os.remove("_last.mkv")
    os.remove("_newseg.mkv")
    os.remove("_tomerge.mkv.lwi")
    print("Cleanup completed.")

def expand_segment_to_iframe(vc_filepath: str, segment_list: list):
    import xml.etree.ElementTree as xet

    os.system('ffprobe -hide_banner -v error -threads auto -show_frames -show_entries frame=key_frame ' +
              f'-of xml -select_streams v:0 -i "{vc_filepath}" > tmp_frames.xml')
    frames = xet.parse("tmp_frames.xml").getroot()[0]
    num_frames = len(frames)
    iseg_list = []
    for seg in segment_list:
        l, r = seg[0], seg[1]
        if l < 0 or l >= num_frames or r < 0 or r >= num_frames:
            raise ValueError(f'Invalid segment [{l}, {r}]')
        while l > 0 and frames[l].attrib['key_frame'] != '1':
            l -= 1
        while r < num_frames and frames[r].attrib['key_frame'] != '1':
            r += 1
        iseg_list += [[l, r]]
    os.remove('tmp_frames.xml')
    return iseg_list


def sort_segment(segment_list: list):
    segment_list = sorted(segment_list, key=lambda x: x[0])
    merge_list = []
    i = 0
    while i < len(segment_list):
        seg = segment_list[i]
        l, r = seg[0], seg[1]
        j = i + 1
        while j < len(segment_list) and segment_list[j][0] <= r:
            r = max(segment_list[j][1], r)
            j += 1
        merge_list += [[l, r]]
        i = j
    return merge_list


def main():
    parser = argparse.ArgumentParser(description="Split, Encode and Merge for HEVC/AVC files.")

    parser.add_argument('input', type=str, help="Path to the input HEVC/AVC file.")
    parser.add_argument('segments', type=str, help="List of segments to process, e.g., [[0, 100], [200, 300]].")
    parser.add_argument('x26x_param', type=str, help="Encoding parameters for x264/x265.")
    parser.add_argument('vapoursynth_script', type=str, help="Path to the VapourSynth script.")
    parser.add_argument('output', type=str, help="Path to the output file.")
    parser.add_argument('--encoder', type=str, choices=['x264', 'x265'], default="x265", help="Select x264 or x265 encoder.")
    parser.add_argument('--qpfile', type=str, help="Path to the QP file (optional).")
    parser.add_argument('--force_expand', action='store_true', help="Force expand segments to I-frames.")

    args = parser.parse_args()

    # Parse segment list from string to list of lists
    segment_list = eval(args.segments)

    SEM(
        fp_vc_input=args.input,
        segment_list=segment_list,
        x26x_param=args.x26x_param,
        fp_vpy=args.vapoursynth_script,
        fp_vc_output=args.output,
        encoder=args.encoder,
        fp_qpfile=args.qpfile,
        force_expand=args.force_expand
    )


if __name__ == "__main__":
    main()
