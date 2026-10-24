# Raspberry Pi Access Control System

## Overview
This project is a hybrid **Access Control and Monitoring System** that integrates physical hardware (Raspberry Pi) with a remote management Web Interface. The system simulates a real-world security environment, featuring rhythmic pattern authentication, intelligent motion detection, and real-time remote administration.

## Key Features

### Advanced Physical Access Control
* **Single-Button Interface:** Operates via a multifunction button for manual locking and unlocking.
* **Rhythmic Authentication:** If the door is locked, the user must input a specific rhythmic pattern to gain access.
* **State Management:** The system handles multiple states including `LOCKED`, `OPEN`, `ALARM`, and `WAITING_CODE`.

### Intelligent Surveillance (PIR Sensor)
The system distinguishes between two operating modes to optimize security:
* **Maximum Security Mode:** Immediate intrusion detection triggers the alarm instantly.
* **Basic Mode:** Applies a "Persistence Filter" to ignore false positives, requiring sustained movement to trigger an alert.

### Remote Web Management
A **Flask-based web server** provides a secure dashboard for administrators:
* **Real-time Monitoring:** View the current status of the door and sensors.
* **Remote Actions:** Open/Close door, toggle Alarm, and switch Day/Night modes.
* **Event Logging:** A comprehensive history of physical and digital events is stored in a SQLite database.

## Project Structure
```
├── pyproject.toml
├── data/                      # SQLite database (generated, git-ignored)
└── src/rpi_access_control/
    ├── __main__.py            # entry point: DB check + hardware/web processes
    ├── config.py              # shared paths
    ├── hardware.py            # GPIO / state machine process
    ├── web.py                 # Flask app
    ├── setup_db.py            # first-run DB + admin creation
    ├── templates/
    └── static/
```

## Usage
```bash
pip install -e .
python -m rpi_access_control      # or: rpi-access-control
```
On first run the database is created interactively (`python -m rpi_access_control.setup_db`).
