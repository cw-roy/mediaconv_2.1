import os
import sys
import re
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import json
import platform
from datetime import datetime
import uuid


"""

Converts video files to .mp4. 

Sets resolution of the converted file to 720p to ensure compatibility
across different players while in many cases reducing file size.

"""
# Define constants for folder names
CONVERT_MEDIA_FOLDER = "convert_media"
CONVERTED_MEDIA_FOLDER = "converted_media"
LOGGING_FOLDER = "logging"

# Set executable for Windows or *nix systems
PLATFORM = platform.system()
FFMPEG = "ffmpeg.exe" if PLATFORM == "Windows" else "ffmpeg"
FFPROBE = "ffprobe.exe" if PLATFORM == "Windows" else "ffprobe"


def check_ffmpeg():
    """
    Confirm FFMpeg is installed
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, check=True
        )
        logging.info(f"FFmpeg version: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error("Error: FFmpeg is not installed or not in the system PATH.")
        logging.error(f"Command output (stderr): {e.stderr.strip()}")
        print("Error: FFmpeg is not installed or not in the system PATH.")
        print(f"Command output (stderr): {e.stderr.strip()}")
        sys.exit(1)  # Exit with an error code


def setup_directories():
    """
    Check and create directories if not present.
    """
    directories = [CONVERT_MEDIA_FOLDER, CONVERTED_MEDIA_FOLDER, LOGGING_FOLDER]

    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logging.info(f"Created directory: {directory}")


def setup_logging(log_directory="logging"):
    """
    Set up logging to a file with a rotating file handler.
    """
    log_file_path = os.path.join(log_directory, "convertlog.log")

    # Rotates the log file every 5 MB and keeps 1 backup
    rotating_handler = RotatingFileHandler(
        log_file_path, maxBytes=5 * 1024 * 1024, backupCount=1
    )

    # Set up the logging format
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    rotating_handler.setFormatter(formatter)

    # Get the root logger and remove any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers = []

    # Add the rotating file handler to the root logger
    root_logger.addHandler(rotating_handler)

    # No need to set the level for the rotating handler; it inherits from the root logger

    # Set the global logging level
    root_logger.setLevel(logging.INFO)

    root_logger.info("Logging initiated.")
    return log_file_path


def generate_batch_id():
    """Generate a unique ID for the conversion batch"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[
        :8
    ]  # Use the first 8 characters of a UUID for uniqueness
    batch_id = f"{timestamp}_{unique_id}"
    logging.info(f"Begin processing conversion batch ID: {batch_id}")
    return batch_id


def prepare_files():
    """
    Check and rename files in the 'convert_media' folder, replacing spaces
    with underscores and removing other non-alphanumeric characters.
    """
    logging.info("Checking filenames for non-standard characters:")

    convert_folder = CONVERT_MEDIA_FOLDER

    files_in_convert = [
        file
        for file in os.listdir(convert_folder)
        if os.path.isfile(os.path.join(convert_folder, file))
    ]

    for file in files_in_convert:
        # Check if the file name contains spaces or other non-alphanumeric characters
        if any(
            char in r'~\/*?<>|:" ' for char in file
        ):  # Include space character in the condition
            # Remove non-alphanumeric characters (excluding spaces)
            new_file_name = re.sub(r"[^a-zA-Z0-9_ .]", "", file)

            # Replace spaces with underscores
            new_file_name = new_file_name.replace(" ", "_")

            # Extract file prefix and extension
            file_prefix, file_extension = os.path.splitext(new_file_name)

            # If the new file name already exists, add a counter to the filename
            counter = 1
            while os.path.exists(
                os.path.join(convert_folder, f"{file_prefix}_{counter}{file_extension}")
            ):
                new_file_name = f"{file_prefix}_{counter}{file_extension}"
                counter += 1

            # Rename the file if it contains spaces or other non-alphanumeric characters
            if file != new_file_name:
                os.rename(
                    os.path.join(convert_folder, file),
                    os.path.join(convert_folder, new_file_name),
                )
                logging.info(f'Renamed file: "{file}" to "{new_file_name}"')

    logging.info("Filenames prepared for processing.")


def validate_files():
    """
    Validate video files by checking if they have a valid video stream.
    Return a list of valid video files.
    """
    valid_video_files = []

    for file in files:
        input_file_path = os.path.join(CONVERT_MEDIA_FOLDER, file)

        try:
            ffprobe_command = [
                FFPROBE,
                "-hide_banner",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                input_file_path,
            ]

            ffprobe_output = subprocess.check_output(
                ffprobe_command, stderr=subprocess.STDOUT, text=True
            )

            # Check if the ffprobe output contains "video"
            if "video" in ffprobe_output.lower():
                valid_video_files.append(file)
            else:
                logging.error(f'File "{file}" does not contain a valid video stream.')
                logging.error(f"ffprobe output for {file}: {ffprobe_output.strip()}")
        except subprocess.CalledProcessError as e:
            # ffprobe command failed
            logging.error(
                f'Error in function `validate_files` running ffprobe for file "{file}".'
            )
            logging.error(f"Returned from ffprobe: {e.output.strip()}")

    return valid_video_files


def inspect_files(valid_video_files):
    """
    Uses ffprobe to log detailed information about valid video files pre-conversion.
    """
    convert_folder = CONVERT_MEDIA_FOLDER

    if not valid_video_files:
        logging.info("No valid video files found in the convert_media folder.")
        return

    logging.info("Inspecting validated files:")

    for file in valid_video_files:
        file_path = os.path.join(convert_folder, file)

        # Use ffprobe to capture detailed information about the file
        ffprobe_command = f'{FFPROBE} -hide_banner -v error -show_entries format=duration,bit_rate,size -show_entries stream=codec_type,width,height,display_aspect_ratio,codec_name -of json "{file_path}"'
        try:
            result = subprocess.check_output(
                ffprobe_command, shell=True, text=True, stderr=subprocess.STDOUT
            )
            data = json.loads(result)

            # Format Duration as HH:MM:SS.ss
            duration_seconds = float(data["format"]["duration"])
            formatted_duration = "{:02}:{:02}:{:.2f}".format(
                int(duration_seconds // 3600),
                int((duration_seconds % 3600) // 60),
                duration_seconds % 60,
            )

            # Format Bitrate in kb/s
            formatted_bitrate = "{:.2f} kb/s".format(
                float(data["format"]["bit_rate"]) / 1000
            )

            # Format Size in MB
            formatted_size_mb = "{:.2f} MB".format(
                float(data["format"]["size"]) / (1024 * 1024)
            )

            logging.info(f"File: {file}")
            logging.info(f"Size: {formatted_size_mb}")
            logging.info(f"Duration: {formatted_duration}")
            logging.info(f"Bitrate: {formatted_bitrate}")

            for stream in data["streams"]:
                if stream["codec_type"] == "video":
                    if "codec_name" in stream:
                        logging.info(f'Video Codec: {stream["codec_name"]}')

                    logging.info(f'Resolution: {stream["width"]}x{stream["height"]}')

                    if "display_aspect_ratio" in stream:
                        logging.info(
                            f'Display Aspect Ratio: {stream["display_aspect_ratio"]}'
                        )
                    else:
                        logging.info("Display Aspect Ratio: Not available")

                elif stream["codec_type"] == "audio":
                    logging.info("Audio: Present")

        except subprocess.CalledProcessError as e:
            # ffprobe command failed
            logging.error(
                f'Error in `inspect_file` function running ffprobe for file "{file}": {str(e)}'
            )

    logging.info("File inspection completed.")


def convert_video(file):
    """
    Converts a video file to .mp4 format, selecting only video and audio streams.
    Specifies the h264 compression standard, balances conversion speed with compression ratio,
    scales the converted video to 720p while handling non-standard aspect ratios, copies audio
    using the aac format at full quality, and enables quick video playback by optimizing file
    for streaming initiation.
    """
    logging.info(f"Start file conversion for file {file}.")
    try:
        file_path = os.path.join(CONVERT_MEDIA_FOLDER, file)
        output_file = get_output_file_path(file)

        # Construct ffmpeg command
        ffmpeg_command = [
            FFMPEG,
            "-hide_banner",
            "-i",
            file_path,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-vf",
            "format=yuv420p",
            "-vf",
            "scale=-2:720",
            "-c:a",
            "aac",
            "-q:a",
            "100",
            "-movflags",
            "faststart",
            output_file,
        ]

        # Execute ffmpeg command and capture output
        result = subprocess.run(ffmpeg_command, capture_output=True, text=True)

        # Log only essential information
        if result.returncode == 0:
            logging.info(f"Conversion complete for file: {file}.")
        else:
            error_message = f'Error converting file "{file}": {result.stderr.strip()}.'
            logging.error(error_message)

    except subprocess.CalledProcessError as e:
        logging.error(f'Error converting file "{file}": {e}.')


def get_output_file_path(file):
    """
    Get the output file path for the converted_media video, handling duplicate filenames.
    """
    convert_folder = CONVERTED_MEDIA_FOLDER
    file_prefix, file_extension = os.path.splitext(file)
    output_file_path = os.path.join(convert_folder, f"{file_prefix}_converted.mp4")

    counter = 1
    while os.path.exists(output_file_path):
        # If file with the same name exists, add a counter to the filename
        output_file_path = os.path.join(
            convert_folder, f"{file_prefix}_converted_{counter}.mp4"
        )
        counter += 1

    return output_file_path


def inspect_converted_files():
    """
    Inspect converted video files in the 'converted_media' folder.
    Log detailed information about the converted videos. Useful for
    comparison to pre-conversion state.
    """
    convert_folder = CONVERTED_MEDIA_FOLDER

    converted_files = [
        file
        for file in os.listdir(convert_folder)
        if os.path.isfile(os.path.join(convert_folder, file))
    ]

    if not converted_files:
        logging.info("No converted video files found in the converted_media folder.")
        return

    logging.info("Inspecting converted files:")

    for file in converted_files:
        file_path = os.path.join(convert_folder, file)

        # Use ffprobe to capture detailed information about the converted file
        ffprobe_command = f'{FFPROBE} -hide_banner -v error -show_entries format=duration,bit_rate,size -show_entries stream=codec_type,width,height,display_aspect_ratio,codec_name -of json "{file_path}"'
        try:
            result = subprocess.check_output(
                ffprobe_command, shell=True, text=True, stderr=subprocess.STDOUT
            )
            data = json.loads(result)

            # Format Duration as HH:MM:SS.ss
            duration_seconds = float(data["format"]["duration"])
            formatted_duration = "{:02}:{:02}:{:.2f}".format(
                int(duration_seconds // 3600),
                int((duration_seconds % 3600) // 60),
                duration_seconds % 60,
            )

            # Format Bitrate in kb/s
            formatted_bitrate = "{:.2f} kb/s".format(
                float(data["format"]["bit_rate"]) / 1000
            )

            # Format Size in MB
            formatted_size_mb = "{:.2f} MB".format(
                float(data["format"]["size"]) / (1024 * 1024)
            )

            logging.info(f"Converted File: {file}")
            logging.info(f"Size: {formatted_size_mb}")
            logging.info(f"Duration: {formatted_duration}")
            logging.info(f"Bitrate: {formatted_bitrate}")

            for stream in data["streams"]:
                if stream["codec_type"] == "video":
                    if "codec_name" in stream:
                        logging.info(f'Video Codec: {stream["codec_name"]}')

                    logging.info(f'Resolution: {stream["width"]}x{stream["height"]}')

                    if "display_aspect_ratio" in stream:
                        logging.info(
                            f'Display Aspect Ratio: {stream["display_aspect_ratio"]}'
                        )
                    else:
                        logging.info("Display Aspect Ratio: Not available")

                elif stream["codec_type"] == "audio":
                    logging.info("Audio: Present")

        except subprocess.CalledProcessError as e:
            # ffprobe command failed
            logging.error(
                f'Error in `inspect_converted_files` function running ffprobe for file "{file}": {str(e)}'
            )

    logging.info("Converted file inspection completed.")


if __name__ == "__main__":
    check_ffmpeg()

    setup_directories()

    log_file_path = setup_logging(log_directory=LOGGING_FOLDER)

    batch_id = generate_batch_id()

    prepare_files()

    files = [
        file
        for file in os.listdir(CONVERT_MEDIA_FOLDER)
        if os.path.isfile(os.path.join(CONVERT_MEDIA_FOLDER, file))
    ]

    valid_video_files = validate_files()

    if valid_video_files:
        inspect_files(valid_video_files)

        for file in valid_video_files:
            convert_video(file)

        inspect_converted_files()

    logging.info(f"Processing complete for batch ID {batch_id}.\n")











#                -------------
#                | So long.  |
#                -------------
#                         \
#                          \
#                           \
#                       _\`.___              ___,"/_
#                    ,'`,-__.-.``=._    _.=``,-.__-.`'.
#                   /,--'-..,7-)/-`"    "'-\(-7,..-'--.\
#                 ,"`.         '            `         ,'".
#                                          /
#                                         /
#                                        /
#                            -----------------------------
#                            | Thanks for all the fish.  |
#                            -----------------------------
