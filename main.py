import datetime
import pathlib
import time
from configparser import ConfigParser
from datetime import timezone

import matplotlib as mpl
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

from selenium import webdriver

TWEETS_XPATH = '//*[@id="react-root"]/div/div/div[2]/main/div/div/div/div/' \
               'div/div[2]/div/div/section/div/div/div/div/div/article'
USERNAME_XPATH = '//*[@id="layers"]/div/div/div/div/div/div/div[2]/div[2]/' \
                 'div/div/div[2]/div[2]/div[1]/div/div/div[5]/label/div/' \
                 'div[2]/div/input'
PASSWORD_XPATH = '//*[@id="layers"]/div/div/div/div/div/div/div[2]/div[2]/' \
                 'div/div/div[2]/div[2]/div[1]/div/div/div[3]/div/label/div/' \
                 'div[2]/div[1]/input'
EXISTS_XPATH = '//*[@id="react-root"]/div/div/div[2]/main/div/div/div/div[1]' \
               '/div/div[2]/div/div/div[2]/div/div[1]/span'

LOG_IN_XPATH = \
    '//*[@id="layers"]/div/div[1]/div/div/div/div/div/div/div[1]/a/div'
COOKIES_XPATH = '//*[@id="layers"]/div/div/div/div/div/div[2]/div[1]'

MAX_ITERATIONS = 99999


def init_driver():
    script_directory = pathlib.Path().absolute()
    chrome_options = Options()
    chrome_options.add_argument(f'user-data-dir={script_directory}\\selenium')
    web_driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options)
    web_driver.implicitly_wait(5)
    return web_driver


driver = init_driver()
tweet_times = []

config_params = {}
last_date = datetime.datetime


def login():
    """Logins to Tweeter with username and password provided"""
    driver.get('https://twitter.com/i/flow/login')
    try:
        username = driver.find_element(by=By.XPATH, value=USERNAME_XPATH)
        username.send_keys(config_params['username'])
        username.send_keys(Keys.ENTER)

        password = driver.find_element(by=By.XPATH, value=PASSWORD_XPATH)
        password.send_keys(config_params['password'])
        password.send_keys(Keys.ENTER)

        driver.find_element(by=By.XPATH, value=COOKIES_XPATH).click()
        driver.get(
            f"https://twitter.com/{config_params['user']}/with_replies")

    except TimeoutError:
        driver.quit()


def process(tweet):
    """Checks if the tweet is from the specified user and gets the date it
    was published, returns True"""
    tweet_basic_data = tweet.text.splitlines()
    if config_params['user'] not in tweet_basic_data[1]:
        return
    if times := tweet.find_elements(by=By.TAG_NAME, value='time'):
        utc_time = times[0].get_dom_attribute('datetime')
        dt_utc = datetime.datetime.strptime(utc_time, '%Y-%m-%dT%H:%M:%S.%fZ')
        dt_local = dt_utc.replace(tzinfo=timezone.utc).astimezone(tz=None)
        str_date = dt_local.date()
        if str_date < last_date:
            return True
        tweet_times.append(dt_local)


def move_and_process(last_tweet=None, batch=0):
    if batch >= MAX_ITERATIONS:
        return
    time.sleep(2)
    actions = ActionChains(driver)
    index = -1

    tweets = driver.find_elements(by=By.XPATH, value=TWEETS_XPATH)
    if last_tweet is not None:
        index = tweets.index(last_tweet)
    if index == len(tweets):
        return
    for tweet in tweets[index + 1:]:
        if process(tweet):
            return

    new_last_tweet = tweets[-1]
    actions.move_to_element(new_last_tweet).perform()

    batch += 1
    move_and_process(new_last_tweet, batch)


def get_dataframes():
    df = pd.DataFrame(tweet_times, columns=['date_with_time'])
    df['date_with_time'] = pd.to_datetime(df['date_with_time'], utc=True,
                                          errors='coerce')
    df['hour_time'] = df['date_with_time'].dt.hour
    df['date_time'] = df['date_with_time'].dt.date
    df['week_day'] = df['date_with_time'].dt.day_name()
    df = df.assign(number_tweets=1)

    df_day_hour = df.groupby(['week_day', 'hour_time']).agg(
        {'number_tweets': 'count'})
    df_day_count = df.groupby('week_day').agg({'number_tweets': 'count'})
    df_hour_count = df.groupby('hour_time').agg({'number_tweets': 'count'})
    df_date_count = df.groupby('date_time').agg({'number_tweets': 'count'})

    df_day_hour.reset_index(inplace=True)
    df_hour_count.reset_index(inplace=True)
    df_day_count.reset_index(inplace=True)
    df_date_count.reset_index(inplace=True)

    return df_day_hour, df_hour_count, df_day_count, df_date_count


def plot():
    global tweet_times
    tweet_times = list(filter(lambda date: isinstance(date, datetime.datetime),
                              tweet_times))
    df_day_hour, df_hour_count, df_day_count, df_date_count = get_dataframes()
    mpl.use('WebAgg')
    fig = make_subplots(rows=2, cols=2,
                        horizontal_spacing=0.15, )

    fig.add_trace(
        go.Scatter(x=df_day_hour["week_day"], y=df_day_hour["hour_time"],
                   mode='markers',
                   marker=dict(size=df_day_hour['number_tweets'] * 3)),
        row=1, col=1)

    fig.add_trace(
        go.Bar(x=df_hour_count['hour_time'], y=df_hour_count['number_tweets']),
        row=1, col=2)

    fig.add_trace(
        go.Bar(x=df_day_count['week_day'], y=df_day_count['number_tweets']),
        row=2, col=1)

    fig.add_trace(
        go.Bar(x=df_date_count['date_time'],
               y=df_date_count['number_tweets']),
        row=2, col=2)

    fig.update_xaxes(title_text="Week day", row=1, col=1)
    fig.update_xaxes(title_text="Hours", row=1, col=2)
    fig.update_xaxes(title_text="Week day", row=2, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=2)

    # Update yaxis properties
    fig.update_yaxes(title_text="Hours", row=1, col=1)
    fig.update_yaxes(title_text="Tweet count", row=1, col=2)
    fig.update_yaxes(title_text="Tweet count", row=2, col=1)
    fig.update_yaxes(title_text="Tweet count", row=2, col=2)

    fig.update_layout(title={
        'text': 'Tweets analysis',
        'x': 0.5,
        'xanchor': 'center'
    }, showlegend=False)
    fig.show()


def get_params(filename='config.ini', section='tweeter'):
    parser = ConfigParser()
    parser.read(filename)

    if not parser.has_section(section):
        raise Exception(
            'Section {0} not found in the {1} file'.format(section, filename))

    params = parser.items(section)
    for param in params:
        config_params[param[0]] = param[1]


def check_can_access_user():
    exist_span = driver.find_elements(by=By.XPATH, value=EXISTS_XPATH)
    if exist_span:
        return False
    return True


def init_last_date():
    global last_date
    last_date = datetime.datetime.strptime(config_params['last_date'],
                                           '%Y/%m/%d').date()


def main():
    get_params()
    init_last_date()
    driver.get(f"https://twitter.com/{config_params['user']}/with_replies")

    try:
        if driver.find_elements(by=By.XPATH, value=LOG_IN_XPATH):
            login()
        if not check_can_access_user():
            print(
                f"User with name {config_params['user']} can not be accessed")
            return
        time.sleep(5)
        move_and_process()
        plot()

    finally:
        driver.quit()


if __name__ == '__main__':
    main()
