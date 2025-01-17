import json
from datetime import timedelta, datetime, date
import math
import pandas as pd
import numpy as np
from requests_oauthlib import OAuth2Session
from urllib.parse import urlparse, parse_qs
from lambda_decorators import cors_headers
import fitbit
import requests
import base64
import os 
import logging
logging.basicConfig(level=logging.DEBUG)

if os.environ['STAGE'] == 'dev':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

if os.environ['STAGE'] == 'prod':
    # cors_url = 'https://www.understandyoursleep.com'
    cors_url = 'http://localhost:8000'
else:
    cors_url = 'http://localhost:8000'

"""
Global Variables
"""
client_id = os.environ['CLIENT_ID']
client_secret = os.environ['CLIENT_SECRET']
scope = ['sleep']
redirect_url = os.environ['REDIRECT_URL']
url = 'https://www.fitbit.com/oauth2/authorize'
token_url = 'https://api.fitbit.com/oauth2/token'
token_state_url = 'https://api.fitbit.com/1.1/oauth2/introspect'
token_validation_url = 'https://api.fitbit.com/1.1/oauth2/introspect'
response_type = 'code'
prompt = 'login'

"""
Oauth (Authorization)
Set up Oauth Session
"""
oauth = OAuth2Session(
    client_id,
    redirect_uri=redirect_url,
    scope=scope
)

"""
@--------------@
Fitbit API Oauth - Authorization
@--------------@
"""
@cors_headers(origin=cors_url)
def auth(event, context):
    """
    Oauth (Authorization)
    Make Fitbit API authorization request
    """
    authorization_url, state = oauth.authorization_url(
        url
    )

    response = {
        "statusCode": 200,
        "body": json.dumps(authorization_url)
    }

    return response

"""
@--------------@
Fitbit API Oauth - Access Token Generation
@--------------@
"""
@cors_headers(origin=cors_url)
def generate_access_token(event, context):
    
    fitbit_code = event['queryStringParameters']['code']
    fitbit_state = event['queryStringParameters']['state']
    start_date = event['queryStringParameters']['start_date']
    end_date = event['queryStringParameters']['end_date']

    if 'queryStringParameters' in event and 'access_token' in event['queryStringParameters']:
        if event['queryStringParameters']['access_token'] != '':
            fitbit_access_token = event['queryStringParameters']['access_token']
        else:
            fitbit_access_token = ''
    if 'queryStringParameters' in event and 'refresh_token' in event['queryStringParameters']:
        if event['queryStringParameters']['refresh_token'] != '':
            fitbit_refresh_token = event['queryStringParameters']['refresh_token']
        else:
            fitbit_refresh_token = ''
    if 'queryStringParameters' in event and 'user_id' in event['queryStringParameters']:
        if event['queryStringParameters']['user_id'] != '':
            fitbit_user_id = event['queryStringParameters']['user_id']
        else:
            fitbit_user_id = ''
    

    fitbit_authorization_response = str(redirect_url + "?code=" + fitbit_code + "&state=" + fitbit_state)

    """
    Oauth (Fetch Token)
    Fetch access_token to make requests to Fitbit API
    """
    if fitbit_access_token == '':
        
        token = oauth.fetch_token(
            token_url,
            code=fitbit_code,
            authorization_response=fitbit_authorization_response,
            auth=(client_id, client_secret),
            state=fitbit_state
        )

        access_token = token['access_token']
        refresh_token = token['refresh_token']
        user_id = token['user_id']

    else:
        """
        Check access_token status with validation request
        """
        validation_code = str('Bearer ' + fitbit_access_token)

        token_validation = requests.post(
            token_validation_url,
            data={
                "token": fitbit_access_token,
            },
            headers={
                "Authorization": validation_code
            }
        )

        token_status = token_validation.json()['active']
        
        if token_status == False:
            """
            Store token information for Fitbit API requests from token refresh
            """
            token_refresh_url = token_url

            token_refresh = oauth.refresh_token(
                token_refresh_url,
                refresh_token = fitbit_refresh_token,
                auth=(client_id, client_secret)
            )
            # Use refreshed token value
            access_token = token_refresh['access_token']
            refresh_token = token_refresh['refresh_token']
            user_id = token_refresh['user_id']
        else:
            """
            Store token information for Fitbit API requests from request query parameter or authorization
            """
            access_token = fitbit_access_token
            refresh_token = fitbit_refresh_token
            user_id = fitbit_user_id

        # Use query parameter tokens from request
        if fitbit_access_token == '':
            access_token = token['access_token']
            refresh_token = token['refresh_token']
            user_id = token['user_id']
        else:
        # Use tokens generated by authorization
            access_token = fitbit_access_token
            refresh_token = fitbit_refresh_token
            user_id = fitbit_user_id

    sleep_data = get_sleep_logs(access_token, refresh_token, user_id, start_date, end_date)

    response = {
        "statusCode": 200,
        "body": json.dumps({
            "sleep_data": [sleep_data],
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_id
        })
    }

    return response

"""
@--------------@
Fitbit API 'Sleep' Call
@--------------@
"""

def get_sleep_logs(access_token, refresh_token, user_id, start_date, end_date):
    access_token = access_token
    refresh_token = refresh_token
    user_id = user_id
    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')

    """
    Fitbit API server
    """
    fitbit_api_call = fitbit.Fitbit(
        client_id, 
        client_secret, 
        oauth2=True, 
        access_token=access_token, 
        refresh_token=refresh_token
    )

    """
    Fitbit 'Sleep' API call for GET sleep logs by date range
    Resource: https://dev.fitbit.com/build/reference/web-api/sleep/#get-sleep-logs
    """

    sleep_list = []

    # Extract and format Sleep data
    def sleep_data(date):
        fitbit_data = fitbit_api_call.sleep(date=date)
    
        if len(fitbit_data['sleep']) == 0:
            sleep_list.append({
                "sleep_date": date
            })
        elif len(fitbit_data['summary']) == 0:
            sleep_list.append({
                "sleep_date": date
            })
        else:
            sleep_stat = fitbit_data['sleep'][0]
            sleep_summary = fitbit_data['summary']

            sleep_deep = 0
            sleep_light = 0
            sleep_rem = 0
            sleep_wake = 0
            
            if 'stages' in sleep_summary:
                sleep_deep = sleep_summary['stages']['deep']
                sleep_light = sleep_summary['stages']['light']
                sleep_rem = sleep_summary['stages']['rem']
                sleep_wake = sleep_summary['stages']['wake']

            sleep_list.append({
                "sleep_date": sleep_stat['dateOfSleep'],
                "awakenings": sleep_stat['awakeningsCount'],
                "restless": sleep_stat['restlessCount'],
                "awake": sleep_stat['awakeCount'],
                "minutes_asleep": sleep_stat['minutesAsleep'],
                "minutes_awake": sleep_stat['minutesAwake'],
                "minutes_fall_asleep": sleep_stat['minutesToFallAsleep'],
                "minutes_after_wakeup": sleep_stat['minutesAfterWakeup'],
                "minutes_asleep": sleep_summary['totalMinutesAsleep'],
                "minutes_in_bed": sleep_summary['totalTimeInBed'],
                "deep": sleep_deep,
                "light": sleep_light,
                "rem": sleep_rem,
                "wake": sleep_wake,
                "start_time": sleep_stat['startTime'],
                "end_time": sleep_stat['endTime'],
            })

    def daterange(start_date, end_date):
        for n in range(int((end_date - start_date).days)):
            yield start_date + timedelta(n)

    for single_date in daterange(start_date, end_date):
        date_iter = single_date.strftime("%Y-%m-%d")
        sleep_data(date_iter)
    
    jsonData = json.dumps(sleep_list)

    sleep_data = adjust_data_structure(jsonData)

    return sleep_data

    # return response

def adjust_data_structure(jsonObj):
    # Create empty JSON blob
    output_json = {}
    # Import data
    df = pd.read_json(jsonObj)

    # Add column for sleep_date_dow
    df['sleep_date_dow'] = pd.to_datetime(df['sleep_date'], format="%Y/%m/%d").dt.day_name()

    # Add column for HH:MM
    df['minutes_asleep_hhmm'] = df['minutes_asleep'].map(lambda x: str(timedelta(minutes=x))[:-3], na_action='ignore')
    df['minutes_asleep_hhmm_int'] = df['minutes_asleep_hhmm'].str.replace(':','.')

    """
    Time Asleep by Date (Line Graph)
    """
    # Add to JSON output
    output_json['count_time_asleep_timeseries'] = []

    for i, j, k in zip(
        df.sleep_date.dropna().to_list(), 
        df.minutes_asleep.dropna().to_list(), 
        df.minutes_asleep_hhmm.dropna().to_list()
    ):
        output_json['count_time_asleep_timeseries'].append(dict(x=i, y=j, label=k))
    
    """
    Distribution of Time Asleep by H:MM (Histogram)
    """
    # Add to JSON output
    output_json['count_distribution_time_asleep'] = []

    for i in df.minutes_asleep_hhmm_int.dropna().to_list():
        output_json['count_distribution_time_asleep'].append(dict(x=i))

    """
    Bed and Wake Time Distirbution (Scatter)
    """
    # Add to JSON output
    output_json['count_time_awake_asleep_timeseries'] = []

    for i, j, k in zip(df.start_time.dt.time.dropna().astype(str).to_list(), df.end_time.dt.time.dropna().astype(str).to_list(),df.start_time.dt.date.dropna().astype(str).to_list()):
        output_json['count_time_awake_asleep_timeseries'].append(dict(x=i, y=j, asleep_date=k))

    """
    Count of Awakenings
    """
    # Add to JSON output
    output_json['count_sleep_disruptions'] = []

    for i, j, k, l in zip(
        df.sleep_date.dropna().to_list(), 
        df.awakenings.dropna().to_list(),
        df.restless.dropna().to_list(),
        df.awake.dropna().to_list()
    ):
        output_json['count_sleep_disruptions'].append(dict(x=i, awakenings=j, restless=k, awake=l))

    """
    Average Hours Distribution by Day of Week
    """
    # average minutes asleep
    asleep_dow = df[['sleep_date_dow','minutes_asleep_hhmm_int']].copy()

    # convert time to float
    asleep_dow['minutes_asleep_hhmm_int'] = asleep_dow['minutes_asleep_hhmm_int'].astype(float)

    # drop nan values
    asleep_dow.dropna(inplace=True)

    asleep_dow_mean = asleep_dow.groupby('sleep_date_dow').mean()
    dow_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    asleep_dow_mean = asleep_dow_mean.reindex(dow_order)

    # Add to JSON output
    output_json['avg_distribution_sleep_dow'] = []

    for i, j in zip(asleep_dow_mean.index.to_list(), asleep_dow_mean.minutes_asleep_hhmm_int.dropna().to_list()):
        output_json['avg_distribution_sleep_dow'].append(dict(x=i, y=j))

    """
    Light vs Deep vs REM (Pie Chart)
    """
    # average minutes asleep
    sleep_type_df = df[['deep','light','rem']].copy()

    # drop nan values
    sleep_type_df.dropna(inplace=True)
    
    # drop zero values
    sleep_type_df = sleep_type_df[(sleep_type_df.T != 0).any()]

    # sum columns
    sleep_type_sum = sleep_type_df.sum()

    # sum row and column totals
    sleep_type_df.loc['column_total']= sleep_type_df.sum(numeric_only=True, axis=0)
    sleep_type_df.loc[:,'row_total'] = sleep_type_df.sum(numeric_only=True, axis=1)

    # extract grand total
    sleep_type_sum_gtotal = sleep_type_df.iloc[-1,-1]

    # convert sum to % of total
    sleep_type_perc = pd.DataFrame((sleep_type_sum / sleep_type_sum_gtotal) * 100, columns=['total'])

    # Add to JSON output
    output_json['avg_distribution_sleep_type'] = []

    for i, j in zip(sleep_type_perc['total'].dropna().to_list(), sleep_type_perc.index.to_list()):
        output_json['avg_distribution_sleep_type'].append(dict(x=i, y=j))

    """
    Average Times Awake by DoW (Histogram)
    """

    df_awake = df[['sleep_date_dow','awake']].copy().dropna()

    awake_dow_mean = df_awake.groupby('sleep_date_dow').mean()

    dow_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    awake_dow_mean = awake_dow_mean.reindex(dow_order)

    # Add to JSON output
    output_json['avg_distribution_times_awake_dow'] = []

    for i, j in zip(awake_dow_mean.index.to_list(), awake_dow_mean.awake.dropna().to_list()):
        output_json['avg_distribution_times_awake_dow'].append(dict(x=i, y=j))
    
    """
    Bed and Rise Time
    """
    # bed and rise time df
    bed_rise_df = df[['start_time','end_time',]].copy().dropna()

    # Give start and end time a timezone
    start_time = df['start_time'].dt.tz_localize('UTC')
    end_time = df['end_time'].dt.tz_localize('UTC')

    # convert UTC to local and convert to time
    local = 'US/Eastern'
    bed_rise_df['start_time'] = bed_rise_df.start_time.dt.tz_localize(local).dt.time
    bed_rise_df['end_time'] = bed_rise_df.end_time.dt.tz_localize(local).dt.time

    # average times
    bed_time_mean = pd.to_timedelta(bed_rise_df['start_time'].astype(str)).mean()
    wake_time_mean = pd.to_timedelta(bed_rise_df['end_time'].astype(str)).mean()

    # Add to JSON output
    output_json['avg_bed_wake_time'] = [{
        'x': str(bed_time_mean),
        'y': str(wake_time_mean)
    }]

    """
    Average Awakenings, Awake and Restless
    """
    output_json['avg_count_awake'] = [round(df.awake.dropna().mean(),1)]
    output_json['avg_count_awakenings'] = [round(df.awakenings.dropna().mean(),1)]
    output_json['avg_count_restless'] = [round(df.restless.dropna().mean(),1)]

    def validateJSON(jsonData):
        try:
            convertedData = json.dumps(jsonData)
            json.loads(convertedData)
        except ValueError as err:
            return False
        return True

    return output_json
