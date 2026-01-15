# 📚 AI Personalized Storybook Generator

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flask](https://img.shields.io/badge/Flask-Web%20Dashboard-green)
![Stable Diffusion](https://img.shields.io/badge/AI-Stable%20Diffusion%20Forge-orange)
![Automation](https://img.shields.io/badge/Tools-Selenium%20%26%20API-purple)

A comprehensive AI automation system designed to create **personalized storybooks** for children. By leveraging **Stable Diffusion**, **InstantID**, and **ControlNet**, this tool processes student photos in batch to generate consistent story illustrations where the main character retains the student's facial identity across different scenes.

## 🚀 Key Features

* **Identity Preservation:** Uses **InstantID** and **ControlNet** pipelines to maintain facial consistency of students in various artistic styles (e.g., 3D render, watercolor, cartoon).
* **Hybrid Automation Core:**
    * **API Mode:** Direct integration with Stable Diffusion WebUI API for high-speed generation.
    * **UI Automation Mode:** Uses **Selenium** and **Playwright** to interact with the SD WebUI Forge interface directly (useful for complex workflows or specific extensions like REActor not fully exposed via API).
* **Web-Based Management:** A **Flask** dashboard to manage books, pages, prompts, and generation queues.
* **Batch Processing:** Reads student data (names, classes, photos) from **Excel/CSV** files and automates the creation of hundreds of unique pages.
* **Dynamic Prompting:** Supports variables like `{Name}`, `{Class}`, and `{Gender}` in prompts to auto-customize stories (e.g., *"A brave {Gender} exploring a magical forest"*).
* **Face Swap Integration:** Optional post-processing using **REActor** to refine facial details.

## 🏗️ System Architecture

The project consists of a central web server and modular runners:

1.  **`app.py` (Core):** The Flask application. It manages the database (JSON files), serves the UI, and orchestrates the job queue.
2.  **`runner_api.py`:** A worker script that handles generation via HTTP requests to the SD WebUI API. It constructs complex ControlNet payloads dynamically.
3.  **`runner_ui_prompts.py`:** A Selenium-based bot that automates the browser interactions for the WebUI Forge interface, handling file uploads and button clicks programmatically.
4.  **`runner_playwright.py`:** An alternative automation module using Microsoft Playwright for robust browser control.

## 🛠️ Installation & Setup

### Prerequisites

* **Python 3.10+**
* **Stable Diffusion WebUI (Forge Edition recommended):** Must be installed and running.
* **Google Chrome:** Required for Selenium automation.
* **AI Models:**
    * SDXL Checkpoint (e.g., Juggernaut XL).
    * ControlNet Models: `ip-adapter_instant_id_sdxl` and `control_instant_id_sdxl`.
    * (Optional) REActor extension for SD WebUI.

### Steps

1.  **Clone the Repository**
    ```bash
    git clone [https://github.com/yourusername/ai-storybook-generator.git](https://github.com/yourusername/ai-storybook-generator.git)
    cd ai-storybook-generator
    ```

2.  **Install Dependencies**
    ```bash
    pip install flask requests pillow pandas openpyxl selenium webdriver-manager playwright
    playwright install  # If using the Playwright runner
    ```

3.  **Configure Paths**
    Open `app.py` and configure your default directories:
    ```python
    DEFAULT_FACES_DIR = r"C:\path\to\student_photos"
    DEFAULT_OUT_DIR   = r"C:\path\to\output_gallery"
    ```

4.  **Start Stable Diffusion**
    Run your SD WebUI Forge with the API flag enabled:
    ```bash
    ./webui.bat --api --listen
    ```

5.  **Run the Application**
    ```bash
    python app.py
    ```
    Access the dashboard at `http://127.0.0.1:5055`.

## 📖 Usage Guide

1.  **Create a Book:** Go to the dashboard and click "New Book".
2.  **Data Source:** Link an Excel file containing student names and photo paths, or point to a folder of images.
3.  **Design Pages:** Add pages to your book. Write prompts using placeholders:
    > *Prompt: "A cinematic shot of {Name} wearing a space suit, standing on Mars, 8k, detailed"*
4.  **Configure Identity:** Enable ControlNet and select "InstantID" to ensure the generated character looks like the student.
5.  **Generate:**
    * Click **"Run via API"** for background processing.
    * Click **"Run via Forge UI"** to watch the browser automation in action (useful for debugging or specific rendering pipelines).

## 📂 Project Structure

```text
ai-storybook-generator/
├── app.py                  # Main Flask Server & UI
├── runner_api.py           # SD API integration logic
├── runner_ui_prompts.py    # Selenium automation logic
├── runner_playwright.py    # Playwright automation logic
├── data/
│   ├── books/              # JSON storage for book configurations
│   └── logs/               # Execution logs
└── templates/              # HTML templates for the dashboard (embedded in app.py)

🔧 Tech Stack
Backend: Python, Flask

Automation: Selenium WebDriver, Playwright

Data Processing: Pandas, OpenPyXL

AI Integration: Stable Diffusion API, ControlNet, InstantID, REActor

🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the issues page.

📄 License
This project is licensed under the MIT License.
