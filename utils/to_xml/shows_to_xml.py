import os
import json
import xml.etree.ElementTree as ET
import pandas as pd

import importlib
from utils.step_utils import create_step

def calculate_start_time(previous_time, signature, bpm, num_bars, transition, previous_bpm=None):
    """
    Calculate the start time in milliseconds with normalized beat calculations
    Parameters:
        previous_time: Previous start time in milliseconds
        signature: Time signature as string (e.g. "4/4")
        bpm: Target BPM for this section
        num_bars: Number of bars
        transition: Type of transition ("instant" or "gradual")
        previous_bpm: BPM of the previous section (needed for gradual transition)
    Returns:
        int: New start time in milliseconds
    """
    numerator, denominator = map(int, signature.split('/'))
    # Normalize to quarter notes for consistent calculation
    beats_per_bar = (numerator * 4) / denominator

    if transition == "instant" or previous_bpm is None:
        milliseconds_per_bar = (60000 / bpm) * beats_per_bar
        return previous_time + int(milliseconds_per_bar * num_bars)

    elif transition == "gradual":
        total_time = 0
        for bar in range(num_bars):
            # Using a slightly curved interpolation instead of linear
            progress = (bar / num_bars) ** 0.52  # Adding slight curve to the transition
            current_bpm = previous_bpm + (bpm - previous_bpm) * progress
            milliseconds_per_bar = (60000 / current_bpm) * beats_per_bar
            total_time += milliseconds_per_bar

        return previous_time + int(total_time)

    else:
        raise ValueError(f"Unknown transition type: {transition}")


def create_sequence(root, sequence_id, sequence_name, bound_scene_id):
    """
    Creates a Sequence function element
    Parameters:
        root: The root XML element to add the sequence to
        sequence_id: ID of the sequence
        sequence_name: Name of the sequence
        bound_scene_id: ID of the bound scene
    Returns:
        Element: The created sequence element
    """
    sequence = ET.SubElement(root, "Function")
    sequence.set("ID", str(sequence_id))
    sequence.set("Type", "Sequence")
    sequence.set("Name", sequence_name)
    sequence.set("BoundScene", str(bound_scene_id))

    speed = ET.SubElement(sequence, "Speed")
    speed.set("FadeIn", "0")
    speed.set("FadeOut", "0")
    speed.set("Duration", "0")

    direction = ET.SubElement(sequence, "Direction")
    direction.text = "Forward"

    run_order = ET.SubElement(sequence, "RunOrder")
    run_order.text = "SingleShot"

    speed_modes = ET.SubElement(sequence, "SpeedModes")
    speed_modes.set("FadeIn", "PerStep")
    speed_modes.set("FadeOut", "PerStep")
    speed_modes.set("Duration", "PerStep")

    return sequence


def create_tracks(function, root, base_dir="../"):
    """
    Creates Track elements, Scenes, and Sequences for each channel group category
    Parameters:
        function: The Function XML element (show) to add tracks to
        root: The root XML element where scenes will be added
        base_dir: Base directory path
    Returns:
        int: Next available ID
    """
    # Convert relative paths to absolute paths
    base_dir = os.path.abspath(base_dir)
    groups_file = os.path.join(base_dir, 'setup', 'groups.csv')
    show_name = function.get('Name')
    structure_file = os.path.join(base_dir, 'shows', show_name, f"{show_name}_structure.csv")  # Added .csv extension
    values_file = os.path.join(base_dir, 'shows', show_name, f"{show_name}_values.json")

    # Check if required files exist
    if not os.path.exists(groups_file):
        print(f"Groups file not found: {groups_file}")
        return
    if not os.path.exists(structure_file):
        print(f"Structure file not found: {structure_file}")
        return

    # Load the show values if they exist
    show_values = {}
    if os.path.exists(values_file):
        try:
            with open(values_file, 'r') as f:
                values_data = json.load(f)
                for item in values_data:
                    key = (item['show_part'], item['fixture_group'])
                    show_values[key] = item
        except Exception as e:
            print(f"Error loading values file: {e}")

    # Read the CSV files
    groups_df = pd.read_csv(groups_file)
    structure_df = pd.read_csv(structure_file)
    categories = groups_df['category'].unique()
    current_id = int(function.get("ID")) + 1

    track_id = 0
    for category in categories:
        if pd.isna(category) or category == 'None':
            continue

        # Create Track
        track = ET.SubElement(function, "Track")
        track.set("ID", str(track_id))
        track.set("Name", str(category).upper())
        track.set("SceneID", str(current_id))
        track.set("isMute", "0")

        # Create Scene
        scene = ET.SubElement(root, "Function")
        scene.set("ID", str(current_id))
        scene.set("Type", "Scene")
        scene.set("Name", f"Scene for {show_name} - Track {track_id + 1}")
        scene.set("Hidden", "True")

        # Add Speed element
        speed = ET.SubElement(scene, "Speed")
        speed.set("FadeIn", "0")
        speed.set("FadeOut", "0")
        speed.set("Duration", "0")

        # Add ChannelGroupsVal element
        channel_groups = ET.SubElement(scene, "ChannelGroupsVal")
        channel_groups.text = "0,0"

        # Add fixture values
        category_fixtures = groups_df[groups_df['category'] == category]
        for _, fixture in category_fixtures.iterrows():
            fixture_val = ET.SubElement(scene, "FixtureVal")
            fixture_val.set("ID", str(fixture['id']))
            fixture_val.text = ','.join([f"{i},0" for i in range(int(fixture['Channels']))])

        current_id += 1

        # Create sequences for each show part
        start_time = 0
        previous_bpm = None

        for _, row in structure_df.iterrows():
            show_part = row['showpart']
            key = (show_part, category)

            # Get effect data from show_values
            effect_data = show_values.get(key, {})
            effect_name = effect_data.get('effect', '')
            effect_speed = effect_data.get('speed', '1')
            effect_color = effect_data.get('color', '')

            sequence_name = f"{show_name}_{category}_{row['showpart']}"
            sequence = create_sequence(root, current_id, sequence_name, scene.get("ID"))

            # Add effect steps if an effect is specified
            if effect_name=="":
                # Create steps based on effect, speed, and color
                create_step(sequence, effect_name, effect_speed, effect_color)
            else:
                pass

            # Add to track
            show_function = ET.SubElement(track, "ShowFunction")
            show_function.set("ID", str(current_id))
            show_function.set("StartTime", str(start_time))
            show_function.set("Color", row['color'])

            # Calculate next start time
            start_time = calculate_start_time(
                start_time,
                row['signature'],
                row['bpm'],
                row['num_bars'],
                row['transition'],
                previous_bpm
            )

            previous_bpm = row['bpm']
            current_id += 1

        track_id += 1

    return current_id


def create_shows(root, shows_dir='../shows', base_dir='../'):
    """
    Creates show function elements from show files in the shows folder
    Parameters:
        root: The root XML element to add the show functions to
        shows_dir: Directory containing show files
        base_dir: Base directory path
    Returns:
        int: Next available ID
    """
    show_id = 0  # Initialize show ID counter

    # Convert relative paths to absolute paths
    shows_dir = os.path.abspath(shows_dir)
    base_dir = os.path.abspath(base_dir)

    # Get all show folders
    for show_name in sorted(os.listdir(shows_dir)):
        show_path = os.path.join(shows_dir, show_name)

        if os.path.isdir(show_path):
            # Check if all required files exist
            required_files = [
                f"{show_name}_setup.json",
                f"{show_name}_structure.csv",  # Added file extension
                f"{show_name}_values.json"  # Added values file requirement
            ]

            missing_files = [f for f in required_files
                             if not os.path.exists(os.path.join(show_path, f))]

            if not missing_files:
                try:
                    # Create Function element for the show
                    function = ET.SubElement(root, "Function")
                    function.set("ID", str(show_id))
                    function.set("Type", "Show")
                    function.set("Name", show_name)

                    # Read show setup file for configuration
                    setup_file = os.path.join(show_path, f"{show_name}_setup.json")
                    with open(setup_file, 'r') as f:
                        setup_data = json.load(f)

                    # Create TimeDivision element with data from setup
                    time_division = ET.SubElement(function, "TimeDivision")
                    time_division.set("Type", setup_data.get("TimeType", "Time"))
                    time_division.set("BPM", str(setup_data.get("BPM", 120)))

                    # Create tracks for this show and get next available ID
                    next_id = create_tracks(function, root, base_dir)
                    show_id = next_id  # Update show_id for next iteration

                    print(f"Successfully created show: {show_name}")

                except json.JSONDecodeError as e:
                    print(f"Error reading setup file for show {show_name}: {e}")
                except Exception as e:
                    print(f"Error processing show {show_name}: {str(e)}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"Show {show_name} is missing required files: {missing_files}")

    return show_id




