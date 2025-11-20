# owoTracker to OpenTrack Bridge

A lightweight Python application with a graphical user interface that acts as a bridge between an owoTrack-compatible phone app and OpenTrack for head tracking.

## Features

-   **Real-time Data Forwarding:** Receives UDP tracking data from your phone and sends it to OpenTrack.
-   **3D Visualization:** A live 3D view of the tracker's orientation.
-   **Cross-Platform:** Works on Windows, Linux, and macOS.

## Requirements

-   [Python 3](https://www.python.org/downloads/)
-   An owoTrack-compatible tracker app on your phone.
-   [OpenTrack](https://github.com/opentrack/opentrack) installed and running.

## Installation

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/serifpersia/owotracker2opentrack.git
    cd owotracker2opentrack
    ```

2.  **Run the installation script:**
    -   On **Windows**, run `install.bat`.
    -   On **Linux** or **macOS**, run `bash install.sh`.

    This will create a Python virtual environment (`venv`) and install the required dependencies from `requirements.txt`.

## Usage

1.  **Start the Bridge:**
    -   On **Windows**, run `owotracker2opentrack.bat`.
    -   On **Linux** or **macOS**, run `bash owotracker2opentrack.sh`.

2.  **Configure your Phone App:**
    -   Install and open the OwoTracker app on your phone.
    -   Use Auto-connect button or follow manual connection steps below:
    -   Set the target IP address to your computer's local IP address.
    -   Set the port to `6969`.
    -   Start tracking. The bridge application should detect your phone automatically.

3.  **Configure OpenTrack:**
    -   In OpenTrack, set the "Input" tracker to `UDP over network`.
    -   Click the settings button (`...`) next to it and ensure the port matches the port in the bridge application (default is `4242`).

4.  **Using the Bridge UI:**
    -   **OpenTrack Port:** Set the port that OpenTrack is listening on.
    -   **Reset Tracking (Center):** Resets the tracking orientation to the current position. Point your head forward and click this to set the zero point.
    -   **Start/Stop Forwarding:** Toggles sending data to OpenTrack.
    -   **OpenTrack Output Mapping:** Customize how the phone's axes (Yaw, Pitch, Roll) are sent to OpenTrack. You can remap or invert them as needed.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.