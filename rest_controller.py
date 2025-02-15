import psycopg2
import requests
import json
import time
from datetime import timedelta

# PostgreSQL database connection parameters
DB_CONFIG = {
    "host": "localhost",
    "database": "local_db",          # Replace with your database name
    "user": "postgres",           # Replace with your DB username
    "password": "",   # Replace with your DB password
    "port": 5432                      # Default PostgreSQL port
}

# API endpoint to create attendance
ATTENDANCE_API_URL = "http://localhost:8017/send_request?model=hr.attendance"

# Define the headers needed for authentication
headers = {
    "login": "shisokamanuel@gmail.com",
    "password": "pass",
    "api-key": "b70e0cdd-1f8c-494a-a073-1ff779dffa43"
}

try:
    while True:  # Infinite loop
        try:
            # Connect to the PostgreSQL database
            connection = psycopg2.connect(**DB_CONFIG)
            cursor = connection.cursor()

            # Query to retrieve records with sync_status = 'PENDING'
            query = """
            SELECT id, badge_number, check_in_date_time, attendance_status 
            FROM attendance
            WHERE sync_status = 'PENDING'
            ORDER BY id ASC
            """
            cursor.execute(query)

            # Fetch all records with PENDING status
            records = cursor.fetchall()

            if records:
                for record in records:
                    record_id, badge_number, check_in_date_time, attendance_status = record
                    print(f"Processing: ID: {record_id}, Badge Number: {badge_number}, DateTime: {check_in_date_time}, Status: {attendance_status}")

                    # Determine the appropriate field based on attendance_status
                    attendance_field = "check_out" if attendance_status.lower() == "check out" else "check_in"

                    # Subtract 3 hours from the time before sending it
                    adjusted_time = check_in_date_time - timedelta(hours=3)

                    # Create the payload for the API
                    data = {
                        "fields": ["employee_id", attendance_field],
                        "values": {
                            "employee_id": badge_number,
                            attendance_field: adjusted_time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                    }

                    try:
                        # Send data to the Create Attendance endpoint
                        response = requests.post(ATTENDANCE_API_URL, json=data, headers=headers)

                        # Print status code and response content for debugging
                        print(f"Response Status Code: {response.status_code}")
                        print(f"Response Text: {response.text}")

                        if response.status_code in [200, 201]:
                            print(f"Attendance for employee {badge_number} processed successfully.")
                            # Update sync_status to 'PROCESSED' in the database
                            update_query = """
                            UPDATE attendance
                            SET sync_status = 'PROCESSED'
                            WHERE id = %s
                            """
                            cursor.execute(update_query, (record_id,))
                            connection.commit()

                        elif response.status_code == 409:  # Conflict (duplicate entry)
                            print(f"Duplicate attendance for employee {badge_number}.")
                            # Update sync_status to 'DUPLICATE' in the database
                            update_query = """
                            UPDATE access_logs
                            SET sync_status = 'DUPLICATE'
                            WHERE id = %s
                            """
                            cursor.execute(update_query, (record_id,))
                            connection.commit()

                        else:
                            print(f"Failed to process attendance for employee {badge_number}: {response.text}")
                            # Leave sync_status as 'PENDING' to retry in the next iteration

                    except Exception as api_error:
                        print(f"Error sending request for employee {badge_number}: {api_error}")
                        # Leave sync_status as 'PENDING' to retry in the next iteration

            else:
                print("No records with PENDING status. Waiting for new data...")

        except Exception as db_error:
            print(f"Database error: {db_error}")

        finally:
            # Close the database connection
            if cursor:
                cursor.close()
            if connection:
                connection.close()

        # Wait for 30 minutes before the next iteration
        time.sleep(1800)

except KeyboardInterrupt:
    print("Process interrupted by user. Exiting...")
