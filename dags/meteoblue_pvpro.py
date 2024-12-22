"""
meteoblue_pvpro
DAG auto-generated by Astro Cloud IDE.
"""

from airflow.decorators import dag
from astro import sql as aql
import pandas as pd
import pendulum


@aql.dataframe(task_id="extractor")
def extractor_func():
    import requests
    from datetime import datetime, timedelta
    import json
    import psycopg2
    from psycopg2.extras import DictCursor
    import pytz
    
    # Database configuration
    db_config = {
        'host': 'ep-shiny-sun-a2tyqp7j.eu-central-1.pg.koyeb.app',
        'user': 'zengrid-db-test',
        'password': 'LF2hried9YBT',
        'dbname': 'zengrid-test',
        'port': 5432,
        'cursor_factory': DictCursor
    }
    
    # Metering type mapping
    metering_type_mapping = {
        'moduletemperature_instant': 'temperature',
        'snowcover': 'snow_cover',
        'pvpower_instant': 'power_instant',
        'gti_instant': 'gti_instant',
        'performanceratio': 'performance_ratio'
    }
    
    # SQL query to get site data
    sql_query = """
    select
        energy_asset.id as energy_asset_id,
        left(location.latitude, char_length(location.latitude) - 1) as lat,
        left(location.longitude, char_length(location.longitude) - 1) as lon,
        energy_asset.surface_azimuth_angle as facing,
        energy_asset.surface_tilt_angle as slope,
        energy_asset.max_generation as kwp,
        0.18 as power_efficiency,
        622 as asl
    from public.delivery_point
        join public.location on location.id = delivery_point.location_id
        join public.energy_asset on delivery_point.id = energy_asset.delivery_point_id 
        and energy_asset.type = 'FVE'
    """
    
    try:
        # Connect to database and get site data
        print("\nConnecting to database...")
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        print("Executing query to get sites...")
        cursor.execute(sql_query)
        sites_data = cursor.fetchall()
        print(f"Retrieved {len(sites_data)} sites from database")
    
        # API configuration
        base_url = "https://my.meteoblue.com/packages/pvpro-1h_pvpro-15min"
        api_key = "nVUZvGHKiA4zRuCk"
        extracted_data = []
    
        # Get current time and max forecast time in Prague timezone
        prague_tz = pytz.timezone('Europe/Prague')
        current_time = datetime.now(prague_tz)
        max_forecast_time = current_time + timedelta(hours=48)
        created_at = datetime.now(prague_tz).strftime("%Y-%m-%d %H:%M:%S")
    
        print(f"Current time (Prague): {current_time}")
        print(f"Max forecast time (Prague): {max_forecast_time}")
    
        # Process each site
        for site in sites_data:
            params = {
                'lat': site['lat'],
                'lon': site['lon'],
                'asl': site['asl'],
                'kwp': site['kwp'],
                'slope': site['slope'],
                'facing': site['facing'],
                'power_efficiency': site['power_efficiency'],
                'tracker': 0,
                'tz': 'Europe/Prague',
                'format': 'json',
                'apikey': api_key
            }
            
            print(f"Requesting Meteoblue API for site {site['energy_asset_id']}")
            
            response = requests.get(base_url, params=params)
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"API request failed for site {site['energy_asset_id']}: {response.status_code}")
                continue
            
            api_data = response.json()
            
            # Extract 15-minute data
            times = api_data['data_xmin']['time']
            
            # Structure data
            for api_type, mapped_type in metering_type_mapping.items():
                if api_type not in api_data['data_xmin']:
                    print(f"Warning: {api_type} not found in API response, skipping...")
                    continue
                    
                values = api_data['data_xmin'][api_type]
                
                print(f"Processing {api_type} => {mapped_type} ({len(values)} values)")
                
                for time_str, value in zip(times, values):
                    # Convert forecast time to datetime in Prague timezone
                    forecast_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                    forecast_time = prague_tz.localize(forecast_time)
                    
                    # Skip if forecast time is beyond our 48-hour window
                    if forecast_time > max_forecast_time:
                        continue
    
                    record = {
                        'forecast_date': time_str,
                        'created_at': created_at,
                        'energy_asset_id': site['energy_asset_id'],
                        'meteo_source': 'meteoblue',
                        'metering_type': mapped_type,
                        'value': value
                    }
                    extracted_data.append(record)
    
        print(f"Extracted {len(extracted_data)} records within 48-hour window")
    
        # Save first few records for debugging
        print("\nFirst few records (all times in Prague timezone):")
        for i, record in enumerate(extracted_data[:5]):
            print(f"Record {i + 1}:", record)
    
        # Save data to temporary file
        with open('/tmp/meteoblue_data.json', 'w') as f:
            json.dump(extracted_data, f)
        print("Data saved to temporary file")
    
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        print(f"Error type: {type(e)}")
        if 'api_data' in locals():
            print("\nAPI Data Structure:")
            if 'data_xmin' in api_data:
                print("Available fields in data_xmin:", api_data['data_xmin'].keys())
        raise e
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
        print("Database connection closed")

@aql.dataframe(task_id="loader")
def loader_func():
    import psycopg2
    from psycopg2.extras import DictCursor
    import json
    from datetime import datetime
    
    # Read data from temporary file
    print("Reading data from temporary file...")
    with open('/tmp/meteoblue_data.json', 'r') as f:
        data = json.load(f)
    print(f"Retrieved {len(data)} records to process")
    
    # Database connection parameters
    db_config = {
        'host': 'ep-shiny-sun-a2tyqp7j.eu-central-1.pg.koyeb.app',
        'user': 'zengrid-db-test',
        'password': 'LF2hried9YBT',
        'dbname': 'zengrid-test',
        'port': 5432,
        'cursor_factory': DictCursor
    }
    
    print("\nAttempting database connection with configuration:")
    for key in db_config:
        if key != 'password':
            print(f"{key}: {db_config[key]}")
    print("password: [HIDDEN]")
    
    try:
        print("\nConnecting to database...")
        conn = psycopg2.connect(**db_config)
        print("Connection successful!")
        
        cursor = conn.cursor()
        records_processed = 0
    
        # Test database access
        print("\nTesting database access...")
        cursor.execute("SELECT 1")
        print("Basic query successful")
        
        # Verify table structure and constraints
        print("\nFetching table structure...")
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'current_forecast_test'
        """)
        print("Table structure:")
        for col in cursor.fetchall():
            print(f"{col[0]}: {col[1]} (max length: {col[2]})")
    
        print("\nProcessing records...")
        for record in data:
            sql = """
            INSERT INTO public.current_forecast_test 
            (forecast_date, created_at, energy_asset_id, meteo_source, 
             metering_type, value)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (forecast_date, created_at, metering_type, energy_asset_id, meteo_source)
            DO NOTHING
            """
            
            if records_processed < 5:  # Debug first 5 records
                print(f"\nProcessing record {records_processed + 1}:")
                print(f"forecast_date: {record['forecast_date']}")
                print(f"created_at: {record['created_at']}")
                print(f"energy_asset_id: {record['energy_asset_id']}")
                print(f"meteo_source: {record['meteo_source']}")
                print(f"metering_type: {record['metering_type']}")
                print(f"value: {record['value']}")
    
            cursor.execute(sql, (
                record['forecast_date'],
                record['created_at'],
                record['energy_asset_id'],
                record['meteo_source'],
                record['metering_type'],
                record['value']
            ))
            
            records_processed += 1
            
            if records_processed % 100 == 0:
                conn.commit()
                print(f"Processed {records_processed} records")
        
        conn.commit()
        print(f"\nSuccessfully loaded {records_processed} records")
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        print(f"\nError: {str(e)}")
        print(f"Error type: {type(e)}")
        if isinstance(e, psycopg2.DataError):
            print(f"Problem record: {record}")
        raise e
    
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
        print("\nDatabase connection closed")

default_args={
    "email": [
        "daniel.simandlik@zengrid.cz",
    ],
    "email_on_retry": True,
    "email_on_failure": True,
    "retries": 2,
    "execution_timeout": pendulum.duration(seconds=600).as_timedelta(),
    "owner": "Daniel Šimandlík,Open in Cloud IDE",
}

@dag(
    default_args=default_args,
    schedule="0 0 * * *",
    start_date=pendulum.from_format("2024-12-22", "YYYY-MM-DD").in_tz("UTC"),
    catchup=False,
    owner_links={
        "Daniel Šimandlík": "mailto:daniel.simandlik@zengrid.cz",
        "Open in Cloud IDE": "https://cloud.astronomer.io/clz8f8fvu13ma01ldrqm80ul5/cloud-ide/clz8f980t12zh01kxb904nlyj/cm4zpvc2s15ug01m73hi7iyx9",
    },
)
def meteoblue_pvpro():
    extractor = extractor_func()

    loader = loader_func()

    loader << extractor

dag_obj = meteoblue_pvpro()
