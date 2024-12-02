# SBAT Monitoring System

## Overview

The **SBAT Monitoring System** is a Python API designed to monitor and notify users of available driving exam time slots from the SBAT API. The system periodically checks for new available time slots and sends notifications via email and Telegram when new slots open up. It also tracks the total runtime and provides status updates on the monitoring process.

[Watch the Demo Video](https://storage.googleapis.com/random-data-bucket/SBAT-monitoring.mp4)

**Note**: The demo video may be based on an earlier version of the system and could be outdated. For the most up-to-date information, please refer to the documentation or check the API itself.

## Table of Contents

- [Getting Started](#getting-started)
- [Configuration Options](#configuration-options)
- [Design Choices](#design-choices)

## Getting Started

This section explains how to set up the SBAT Monitoring System on your local machine.

**Prerequisites:**

- A SBAT account is required

**Steps:**

1. **Clone the Repository:**

2. **Create a Virtual Environment:**

   It's recommended to create a virtual environment to manage dependencies:

   ```bash
   python -m venv .venv
   ```

   Activate the virtual environment:

   - On Windows:

     ```
     .venv\Scripts\activate
     ```

   - On macOS/Linux:

     ```
     source .venv/bin/activate
     ```

3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Create a .env File:**

   Create a file named `.env` in the root directory of the project and add the following environment variables, replacing the placeholders with your actual values:

   ```bash
   # database Configuration (Required)
   DATABASE_URL=database_url

   # SBAT API Credentials (Required)
   SBAT_USERNAME=your_sbat_username
   SBAT_PASSWORD=your_sbat_passwords

   # Telegram Notification Settings (Optional)
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id

   # Email Notification Settings (Optional)
   SENDER_EMAIL=email_used_to_send_notifications
   SENDER_PASSWORD=email_password
   SMTP_SERVER=smtp.gmail.com # Example for Gmail - adjust if needed
   SMTP_PORT=587 # Typical port for secure email
   ```

5. **Run the Application:**

   ```bash
   uvicorn main:app --reload
   ```

6. **Access the API Documentation:**

   Once the application is running, you can access the API documentation at:
   http://127.0.0.1:8000/docs

## Configuration Options

The `MonitorConfiguration` class defines the configuration settings for the SBAT Monitoring System. Below are the available configuration options, their default values, and descriptions:

- **`license_types`**: `List[Literal["B", "AM"]]`

  - **Description**: A list of driving license types to monitor. Valid values are `"B"` for car licenses and `"AM"` for motorcycle licenses. The license types are based on the codes used by the SBAT API, you can add their respective letters to this list. For example, if the SBAT API introduces a new license type `"C"`, you can include `"C"` in this list to monitor that type as well.
  - **Default Value**: `["B"]`

- **`exam_center_ids`**: `List[int]`

  - **Description**: A list of exam center IDs to check for available time slots. These IDs correspond to specific locations. If the SBAT API adds new exam centers, you can include their respective IDs in this dict found in `api/models.py`

    `{1: "Sint-Denijs-Westrem", 7: "Brakel", 8: "Eeklo", 9: "Erembodegem", 10: "Sint-Niklaas"}`

  - **Default Value**: `[1]` (corresponding to `"Sint-Denijs-Westrem"`)

- **`seconds_inbetween`**: `PositiveInt`
  - **Description**: The interval in seconds between successive checks for new time slots.
  - **Default Value**: `300` (5 minutes)

### Example Configuration

Here’s an example of how you might configure the `MonitorConfiguration`:

```json
{
  "license_types": ["B", "AM"],
  "exam_center_ids": [1, 7, 8],
  "seconds_inbetween": 600
}
```

## Design Choices

- ### Distributed Client-Side Requests: Considerations and Ethical Concerns

  #### Potential Idea:

  At one point, I considered an approach where each user's browser would make API requests directly to the SBAT API. The thought was that by distributing the requests across different IPs and devices, it would be possible to get updates more frequently and allow users to see changes faster.

  #### Why I Didn’t Go This Route:

  Ultimately, I decided against this. While it might have worked technically, it raised ethical concerns. Bypassing rate limits through distributed requests could violate the SBAT API's terms of service. It’s important to respect the rules set by API providers to ensure everyone has fair access to the service.

  So, instead of pushing the limits, I stuck to a more straightforward approach that stays within the guidelines and keeps things fair for everyone.

- ### Cost-Effective and Efficient Hosting

  The API is hosted on a Google Cloud E2 micro instance, which falls under Google's free tier. This allows the API to run 24/7 without incurring costs, making it a highly cost-effective solution. The instance is configured with HTTPS, ensuring secure communication between clients and the server.

  The database used is MongoDB, which is also hosted under a free tier plan. This setup allows for efficient storage and retrieval of user data, monitoring logs, and other relevant information without additional costs.

  The frontend is hosted using GitHub Pages, which is also free, providing a simple and efficient way to manage and deploy the user interface.

- ### Payment Processing with Stripe

  Payments for subscriptions and other services are handled using Stripe, a reliable and secure payment processor. This integration allows for smooth handling of transactions, with all payment events being tracked and managed via Stripe webhooks.

- ### Telegram Bot and Webhooks

  The Telegram bot, used for sending notifications, is integrated into the system via webhooks. This ensures that messages are sent and received in real-time, providing users with timely updates on available driving exam slots. Webhooks are also used to handle events from Stripe, ensuring that subscription statuses and payment events are processed immediately.

- ### Singleton Pattern for SbatMonitor

  The `SbatMonitor` class is designed as a singleton. This design choice ensures that only one instance of the monitor is created and shared across the application. This pattern prevents multiple instances from running concurrently, which could lead to conflicting operations. It also simplifies the management and tracking of the monitoring task's state, providing a consistent and controlled environment.

- ### BaseSettings Configuration

  The application uses a `BaseSettings` class for configuration management. This class centralizes the configuration settings, such as SBAT API credentials and notification preferences, in one place. By using `BaseSettings`, the configuration can be easily managed and updated without altering the core application logic. This design choice enhances maintainability and flexibility, making it easier to adapt to changes in configuration requirements.
