from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import check_password_hash, generate_password_hash
import functools
from datetime import datetime, timedelta
from flask_session import Session
from flask import Flask, render_template, request, flash, redirect, session
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os
import matplotlib.dates
import mpld3
from mpld3 import plugins
import threading
import psycopg2
import plotly.graph_objs as go
import pandas as pd
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
import yfinance as yf
import stock
import numpy as np
from functools import wraps
import matplotlib
matplotlib.use('Agg')


app = Flask(__name__)


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


load_dotenv()
postgres_pw = os.getenv('POSTGRES_SECRET')[1:-1]
postgres_username = os.getenv('POSTGRES_USERNAME')[1:-1]
alphavantage_key = os.getenv('ALPHAVANTAGE_API_KEY')[1:-1]
c = psycopg2.connect(
    "postgres://postgres:4Fi5GQ7q9fRqCBm@frosty-resonance-3482.internal:5432")
# c = psycopg2.connect("postgres://postgres:"+postgres_pw+"@localhost:15432")


def try_connect(c):
    def connect():
        conn = psycopg2.connect(
            "postgres://postgres:4Fi5GQ7q9fRqCBm@frosty-resonance-3482.internal:5432")
        # conn = psycopg2.connect("postgres://postgres:" + postgres_pw+"@localhost:15432")
        return conn
    try:
        cursor = c.cursor()
        cursor.execute('SELECT 1;')
        cursor.close()
        return c
    except Exception as e:
        print(e)
        try:
            c.close()
            c = connect()
            return c
        except Exception as e1:
            print(e1)
            c = connect()
            return c


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def get_browser(stock):
    chrome_options = Options()
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--crash-dumps-dir=/tmp")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_browser = webdriver.Chrome(options=chrome_options)
    safari_options = webdriver.SafariOptions()
    safari_options.add_argument('--ignore-ssl-errors=yes')
    safari_options.add_argument('--ignore-certificate-errors')
    # safari_browser = webdriver.Safari(keep_alive=False, options=safari_options)
    chrome_browser.maximize_window()
    chrome_browser.get('https://finance.yahoo.com/quote/'+stock+'/')
    return chrome_browser


'''
new features:
1. add other markets geh stocks (DAX30 SZ SH), only 30 top results are showed to prevent hang機
    mkt_value of securities value not correct & need to add (in USD) to the table
2. (optional) improve login regis CSS (e.g. registration, forgetpw became email based and pw need to be strong pw; use outside template)
'''


@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        new_col = request.form.get('id')
        if new_col:
            new_col = new_col.split(sep=',')
            result = add_row_result(new_col[0], new_col[1])
            if not result:
                return []
            return result
        id = session.get("user_id")
        # get the stocks and data in separate list
        stocks = request.form.get("stocks").lstrip().split(sep=' ')
        stocks = [name.upper() for name in stocks]
        with open('stocks.csv', 'r') as stock_name_file:
            ticker_list = stock_name_file.read().split(sep=',')
        if not set(stocks).issubset(ticker_list):
            flash("Invalid ticker(s).")
            return redirect("/")
        t = yf.Ticker(stocks[0])
        basic_info = [stocks[0], t.info['longName'],
                      t.info['exchange'], t.info['financialCurrency']]
        stocks = [name.replace(
            '.', '-') if '.' in name and '.T' not in name and '.HK' not in name and '.L' not in name else name for name in stocks]
        request_data = request.form.getlist("data")
        if_error_request = request_data
        if not request_data:
            flash("Please select the data you wish to analyze.")
            return redirect("/")
        conn = try_connect(c)
        cursor = conn.cursor()
        metatable, est_data, est_name, news_data, pr_data, sec_data, request_data, data_id_name, fig = run_result(
            stocks, request_data)
        if metatable == []:
            flash(
                f'Error occurred when getting selected data {if_error_request} for {stocks[0]}. Please try again')
            return render_template("index.html")
        cursor.execute("INSERT INTO search_history (user_id, s_comp, s_content, time) VALUES (%s, %s, %s, %s);",
                       (id, ', '.join(stocks), ', '.join(request_data), datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        cursor.close()
        return render_template("results.html", all_table=[table.to_html(classes='table table-stripped table-hover table-responsive') for table in metatable], est=[estimates.to_html(classes='table table-stripped') for estimates in est_data], est_no=range(len(est_name)), est_name=est_name, news=news_data, pr=pr_data, sec=sec_data, name=request_data, id_name=data_id_name, number=range(len(request_data)), fig=fig.to_html(), info=basic_info)
    else:
        with open('stocks.csv', 'r') as stock_name_file:
            ticker_list = stock_name_file.read().split(sep=',')
        return render_template("index.html", stocks=ticker_list)


def run_result(stocks, request_data):
    try:
        need_selenium_list = ['Financial Ratio', 'Estimates', 'Competitors', 'Performance vs Market', 'Valuation Metrics',
                              'SEC Filings', 'Trading Information', 'Press Release', 'News']
        need_selenium = [i for i in request_data if i in need_selenium_list]
        need_yf = [i for i in request_data if i not in need_selenium_list]
        metatable, news_data, pr_data, sec_data, est_data, est_name = [], [], [], [], [], []
        fig = pd.DataFrame()
        for ticker in stocks:
            if 'Historical Data' in need_yf:
                start_date = request.form.get("start_date")
                end_date = request.form.get("end_date")
                stocks_for_yf_trade_history = request.form.get("stocks")
                # date_check = re.compile(r'^(?:(?:31(-)(?:0?[13578]|1[02]))\1|(?:(?:29|30)(-)(?:0?[13-9]|1[0-2])\2))(?:(?:1[6-9]|[2-9]\d)?\d{2})$|^(?:29(-)0?2\3(?:(?:(?:1[6-9]|[2-9]\d)?(?:0[48]|[2468][048]|[13579][26])|(?:(?:16|[2468][048]|[3579][26])00))))$|^(?:0?[1-9]|1\d|2[0-8])(-)(?:(?:0?[1-9])|(?:1[0-2]))\4(?:(?:1[8-9]\d{2}|20[0-2][1-9]))$')
                if not (start_date and end_date):
                    flash("Please input start date and end date.")
                    return redirect("/")
                else:
                    # convert the string data into date format for date comparison
                    start_date = datetime.strptime(
                        start_date, "%Y-%m-%d").date()
                    end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                    if end_date <= start_date:
                        flash("Start date can't be larger than / equal to end date.")
                        return redirect("/")
                    if start_date >= datetime.now().date():
                        flash("Invalid start date.")
                        return redirect("/")
            if need_yf != []:
                metatable, yf_fail = stock.get_yf_data(
                    metatable, need_yf, ticker)
                request_data = [
                    success for success in request_data if success not in yf_fail]
            if need_selenium != []:
                browser = get_browser(ticker)
                url = f'/quote/{ticker}/'
                for item in need_selenium:
                    if item == 'News':
                        news_data = stock.get_news(browser, url)
                        if news_data == []:
                            flash(
                                f'Relevant news for {ticker} is currently unavailable.')
                            request_data.remove(item)
                    elif item == 'Press Release':
                        pr_data = stock.get_press_release(browser, url)
                    elif item == 'SEC Filings':
                        sec_data = stock.get_sec_filing(browser, url)
                        if sec_data == []:
                            flash(
                                f'Quarterly and annual reports for {ticker} are currently unavailable.')
                            request_data.remove(item)
                    else:
                        get_item = "get_" + item.replace(" ", "_").lower()
                        # to call the respective function
                        data = getattr(stock, f'{get_item}')
                        table = data(browser, url, ticker, 0)
                        # for Estimates only, take all 5 df and append to metatable
                        if type(table) == tuple:
                            est_name = ['Revenue Estimate', 'Earnings Estimate',
                                        'Earnings History', 'Growth Estimate', 'EPS Trend']
                            for idx in range(len(table)):
                                est_data.append(table[idx])
                                # to ensure len(metatable) == len(data_id_name) for html to render
                            metatable.append(pd.DataFrame())
                        # to account for error during selenium process
                        elif type(table) != pd.DataFrame:
                            request_data.remove(item)
                            continue
                        else:
                            metatable.append(table)
                browser.close()
            if 'Historical Data' in need_yf:
                trade_history = yf.download(
                    stocks_for_yf_trade_history, start=start_date, end=end_date, group_by="ticker")
                trade_history.map(lambda x: str("{:.2f}".format(
                    x) if isinstance(x, int) == False else x))
                metatable.append(trade_history)
                fig = go.Figure(data=[go.Candlestick(x=trade_history.index, open=trade_history['Open'],
                                high=trade_history['High'], low=trade_history['Low'], close=trade_history['Close'], name='Stock Data')])
                fig.update_layout(
                    autosize=True, yaxis_title='Stock Price (USD)', xaxis_title='Date')
        data_id_name = [item.replace(" ", "_").lower()
                        for item in request_data]
        return metatable, est_data, est_name, news_data, pr_data, sec_data, request_data, data_id_name, fig
    except Exception as e:
        print(e)


def add_row_result(ticker, datatype):
    try:
        table = run_result([ticker], [datatype])[0]
        t = yf.Ticker(ticker)
        ticker_name = t.info['longName']
        if datatype in ['Balance Sheet', 'Income Statement', 'Cash Flow Statement', 'Valuation Metrics']:
            cols = table[0].columns.values
            table_list = [table[0][col] for col in table[0].columns.values]
            li = [{cols[i]: table_list[i].to_dict()}
                  for i in range(len(table_list))]
            print('normal')
            print(li)
            return [li, ticker_name]
        else:
            t = table[0][ticker].to_dict()
            print('normal')
            return [t]
    except:
        try:
            table = run_result([ticker], [datatype])[0]
            if datatype in ['Balance Sheet', 'Income Statement', 'Cash Flow Statement', 'Valuation Ratio']:
                table_list = [table[0][col] for col in table[0].columns.values]
                li = [table_list[i].to_dict() for i in range(len(table_list))]
                print('need 2 times')
                return li
            else:
                t = table[0][ticker].to_dict()
                print('need 2 times')
                return [t]
        except:
            print('error')
            return 'error'


def cap_graph(history, cursor, id, h, w):
    current_cap = get_updated_porf_value(cursor, id)[3]
    hist = np.append(np.array([datetime.strptime(data[1][:-7], '%Y-%m-%d %H:%M:%S')
                     for data in history]), datetime.today())
    cap = np.append(np.array([float(data[0])
                    for data in history]), current_cap)
    xformatter = matplotlib.dates.DateFormatter('%Y-%m-%d')
    fig, ax = plt.subplots(figsize=(w, h))
    ax.grid(axis="y", alpha=0.2)
    ax.set_facecolor('#F0F8FF')
    ax.locator_params(nbins=4)
    # ax.yaxis.set_label_position("right")
    # ax.yaxis.tick_right()
    plt.gcf().axes[0].xaxis.set_major_formatter(xformatter)
    line, = ax.plot(hist, cap)
    handles, labels = ax.get_legend_handles_labels()
    interactive_legend = plugins.InteractiveLegendPlugin(zip(
        handles, ax.collections), labels, alpha_unsel=0.5, alpha_over=1.5, start_visible=True)
    plugins.connect(fig, interactive_legend)
    ax.set_title('Total Capital')
    html_str = mpld3.fig_to_html(fig, template_type='general')
    return html_str


@app.route('/history', methods=['GET', 'POST'])
@login_required
def history():
    conn = try_connect(c)
    id = session.get("user_id")
    cursor = conn.cursor()
    if request.method == 'POST':
        id = session.get("user_id")
        data = request.form.get('search').split(sep=';')
        stocks = [data[0]]
        t = yf.Ticker(stocks[0])
        basic_info = [stocks[0], t.info['longName'],
                      t.info['exchange'], t.info['financialCurrency']]
        request_data = [i.lstrip() for i in data[1].split(sep=',')]
        metatable, est_data, est_name, news_data, pr_data, sec_data, request_data, data_id_name, fig = run_result(
            stocks, request_data)
        # db.execute("INSERT INTO search_history (user_id, s_comp, s_content, time) VALUES (?, ?, ?, ?);", id, ', '.join(stocks), ', '.join(request_data), datetime.now())
        cursor.execute("INSERT INTO search_history (user_id, s_comp, s_content, time) VALUES (%s, %s, %s, %s);",
                       (id, ', '.join(stocks), ', '.join(request_data), datetime.now()))
        conn.commit()
        cursor.close()
        return render_template("results.html", all_table=[table.to_html(classes='table table-stripped table-hover table-responsive') for table in metatable], est=[estimates.to_html(classes='table table-stripped') for estimates in est_data], est_no=range(len(est_name)), est_name=est_name, news=news_data, pr=pr_data, sec=sec_data, name=request_data, id_name=data_id_name, number=range(len(request_data)), fig=fig.to_html(), info=basic_info)
    else:
        cursor.execute(
            'SELECT * FROM search_history WHERE user_id = %s ORDER BY id DESC', (id, ))
        s_history = cursor.fetchall()
        basic_info = {}
        for row in s_history:
            t = yf.Ticker(row[1])
            basic_info[row[1]] = t.info['longName']
        cursor.execute(
            'SELECT * FROM trade_history WHERE user_id = %s ORDER BY id DESC', (id, ))
        t_history = cursor.fetchall()
        cursor.close()
        # returns a list of tuples instead of a list of dicts
        return render_template('history.html', s_history=s_history, t_history=t_history, info=basic_info)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = try_connect(c)
        cursor = conn.cursor()
        username = request.form.get("username")
        pw = request.form.get("pw")
        check = request.form.get("check")
        cursor.execute("SELECT username from users;")
        registrants = cursor.fetchall()
        if username == "" or pw == "" or check == "":
            flash("Username or password cannot be blank")
            return render_template("register.html")
        if username == pw:
            flash("Password cannot be same as username")
            return render_template("register.html")
        elif pw != check:
            flash("Passwords do not match")
            return render_template("register.html")
        for i in registrants:
            if username == i[0]:
                flash("This username has been taken.")
                return render_template("register.html")
        else:
            cursor.execute("INSERT INTO users (username, pw, capital) VALUES (%s, %s, 1000000);",
                           (username, generate_password_hash(pw)))
            conn.commit()
            cursor.close()
            return redirect('/')
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()
    if request.method == "POST":
        if request.form.get("forgetpw"):
            return redirect("/forget_pw")
        conn = try_connect(c)
        cursor = conn.cursor()
        username = request.form.get("username")
        cursor.execute("SELECT * FROM users WHERE username = %s;",
                       (username, ))
        rows = cursor.fetchall()
        # format for postgres is a tuple (id, username, pw). So index [2] stands for pw
        if rows == [] or not check_password_hash(rows[0][2], request.form.get("password")):
            flash("Wrong username or password")
            return render_template("login.html")
        session["user_id"] = rows[0][0]
        cursor.close()
        return redirect("/")
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


@app.route("/delete_account", methods=['GET', 'POST'])
@login_required
def delete_account():
    if request.method == 'POST':
        conn = try_connect(c)
        cursor = conn.cursor()
        id = session.get("user_id")
        cursor.execute("DELETE FROM search_history WHERE user_id = %s", (id, ))
        cursor.execute("DELETE FROM trade_history WHERE user_id = %s", (id, ))
        cursor.execute(
            "DELETE FROM capital_history WHERE user_id = %s", (id, ))
        cursor.execute(
            "DELETE FROM portfolio WHERE user_id = %s", (id, ))
        cursor.execute("DELETE FROM users WHERE id = %s", (id, ))
        conn.commit()
        session.clear()
        cursor.close()
        flash("Account deleted")
        return redirect("/")
    else:
        return render_template("delete_account.html")


@app.route("/delete_history", methods=['GET', 'POST'])
@login_required
def delete_history():
    if request.method == 'POST':
        conn = try_connect(c)
        cursor = conn.cursor()
        id = session.get("user_id")
        cursor.execute(
            "DELETE FROM search_history WHERE user_id = %s;", (id, ))
        conn.commit()
        cursor.close()
        flash("History deleted")
        return redirect("/")
    else:
        return render_template("delete_history.html")


@app.route("/change_pw", methods=["GET", "POST"])
@login_required
def change_pw():
    if request.method == 'POST':
        id = session.get("user_id")
        conn = try_connect(c)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s;", (id, ))
        fetch = cursor.fetchall()
        username = fetch[0][1]
        old_pw = fetch[0][2]
        new_pw = request.form.get("new_pw")
        new_check = request.form.get("new_check")
        if new_pw == "" or new_check == "":
            flash("Password cannot be blank")
            return render_template("change_pw.html")
        elif new_pw != new_check:
            flash("Passwords do not match")
            return render_template("change_pw.html")
        else:
            if check_password_hash(old_pw, new_pw):
                flash("Please select a new password")
                return render_template("change_pw.html")
            elif new_pw == username:
                flash("Password cannot be same as username")
                return render_template("change_pw.html")
            else:
                cursor.execute("UPDATE users SET pw = %s WHERE id = %s",
                               (generate_password_hash(new_pw), id))
                conn.commit()
                cursor.close()
                flash("Password changed")
                return redirect("/")
    else:
        return render_template("change_pw.html")


@app.route("/forget_pw", methods=["GET", "POST"])
def forget_pw():
    if request.method == 'POST':
        conn = try_connect(c)
        cursor = conn.cursor()
        username = request.form.get("username")
        pw = request.form.get("new_pw")
        new_check = request.form.get("new_check")
        cursor.execute("SELECT username from users;")
        registrants = cursor.fetchall()
        registrants = [i[0] for i in registrants]
        if username not in registrants:
            flash("No account is linked with this username")
            return render_template("forget_pw.html")
        cursor.execute("SELECT pw FROM users WHERE username=%s", (username, ))
        check = cursor.fetchall()[0][0]
        if username == "" or pw == "" or new_check == "":
            flash("Username or password cannot be blank")
            return render_template("forget_pw.html")
        if username == pw:
            flash("Password cannot be same as username")
            return render_template("forget_pw.html")
        elif pw != new_check:
            flash("Passwords do not match")
            return render_template("forget_pw.html")
        elif check_password_hash(check, pw):
            flash("Password cannot be the same as the last one")
            return render_template("forget_pw.html")
        cursor.execute("UPDATE users SET pw = %s WHERE username = %s;",
                       (generate_password_hash(pw), username))
        conn.commit()
        cursor.close()
        return redirect('/')
    else:
        return render_template("forget_pw.html")


@app.route('/trading', methods=['GET', 'POST'])
@login_required
def trading():
    if request.method == "POST":
        id = session.get("user_id")
        ticker = request.form.get('name')
        if ticker:
            raw, ccy, fx_rate = stock.get_basic_info(ticker)
            return [raw, ccy, fx_rate]
        else:
            stock_amt = float(request.form.get('stock_amt'))
            ticker = request.form.get('stock')
            dir = request.form.get('direction')
            px = request.form.get('px').lstrip()
            px = px[3:] if 'HK$' in px else px[1:]
            print(px)
            price = float(px)
            if price == 0:
                flash('Price cannot be 0')
                return redirect("/trading")
            if not (dir and ticker and stock_amt):
                flash("Details missing.")
                return render_template('trading.html')
            ccy, fx_rate = stock.get_basic_info(ticker)[1:]
            conn = try_connect(c)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT capital FROM users WHERE id = %s;', (id, ))
            capital = cursor.fetchall()
            cursor.execute(
                'SELECT * FROM portfolio WHERE user_id = %s AND stock = %s;', (id, ticker))
            pretrade_portfo = cursor.fetchall()
            value = stock_amt * price
            usd_value = value / fx_rate
            print(value, usd_value)
            new_capital = capital[0][0] - \
                usd_value if dir == 'buy' else capital[0][0] + usd_value
            if new_capital < 0:
                flash(
                    f"Not enough capital to buy {stock_amt} of {ticker}. Your available capital is {capital[0][0] + usd_value}.")
                return render_template('trading.html')
            if not pretrade_portfo:
                cursor.execute("INSERT INTO portfolio (user_id, stock, dir, stock_amt, px_enter, time_enter, val_enter) VALUES (%s, %s, %s, %s, %s, %s, %s);", (
                    id, ticker, dir, stock_amt, price, datetime.now(), value))
                conn.commit()
            else:
                if dir == pretrade_portfo[0][2]:
                    update_value = float(pretrade_portfo[0][5]) + value
                    update_amt = float(pretrade_portfo[0][6]) + stock_amt
                    update_px = (float(pretrade_portfo[0][3])*float(
                        pretrade_portfo[0][6]) + stock_amt*price)/(float(pretrade_portfo[0][6])+stock_amt)
                    cursor.execute("UPDATE portfolio SET stock_amt = %s, px_enter = %s, val_enter = %s WHERE stock = %s;",
                                   (update_amt, update_px, update_value, ticker))
                    conn.commit()
                else:
                    pricedelta = price - pretrade_portfo[0][3]
                    realizedpl = stock_amt * pricedelta if dir == 'buy' else stock_amt * -pricedelta
                    update_amt = float(pretrade_portfo[0][6]) - stock_amt
                    if update_amt == 0:
                        cursor.execute(
                            "DELETE FROM portfolio WHERE stock = %s;", (ticker, ))
                        conn.commit()
                    elif update_amt > 0:
                        update_value = float(pretrade_portfo[0][5]) - value
                        update_px = (float(pretrade_portfo[0][3])*float(
                            pretrade_portfo[0][6]) - stock_amt*price)/(float(pretrade_portfo[0][6])-stock_amt)
                        print(update_value, update_amt, update_px)
                        cursor.execute(
                            "UPDATE portfolio SET stock_amt = %s, px_enter = %s, val_enter = %s WHERE stock = %s;", (update_amt, update_px, update_value, ticker))
                        conn.commit()
                    else:
                        cursor.execute("UPDATE portfolio SET dir = %s, stock_amt = %s, px_enter = %s, val_enter = %s WHERE stock = %s;", (
                            dir, abs(update_amt), price, abs(update_amt)*price), ticker)
                        conn.commit()
            cursor.execute("INSERT INTO trade_history (user_id, stock, dir, stock_amt, px_enter, time_enter, val_enter) VALUES (%s, %s, %s, %s, %s, %s, %s);", (
                id, ticker, dir, stock_amt, price, datetime.now(), value))
            conn.commit()
            update_cap = get_updated_porf_value(cursor, id)[3]
            cursor.execute(
                "INSERT INTO capital_history (user_id, capital, time) VALUES (%s, %s, %s);", (id, update_cap, datetime.now()))
            conn.commit()
            # cursor.execute('SELECT * FROM portfolio WHERE user_id = %s ORDER BY id DESC', (id, ))
            # posttrade_portfo = cursor.fetchall()
            # last_price = {i[1]: float("{:.2f}".format(yf.Ticker(i[1]).fast_info['lastPrice'])) for i in posttrade_portfo}
            cursor.execute(
                "UPDATE users SET capital = %s WHERE id = %s", (new_capital, id))
            conn.commit()
            cursor.close()
            return redirect("/portfo")
    else:
        return render_template("trading.html")


@app.route('/portfo', methods=['GET', 'POST'])
@login_required
def portfolio():
    id = session.get("user_id")
    ticker = request.form.get('name')
    if ticker:
        return "{:.2f}".format(yf.Ticker(ticker).fast_info['lastPrice'])
    conn = try_connect(c)
    cursor = conn.cursor()
    if request.method == "POST":
        req_data = request.form.get('id')
        if req_data:
            portf, last_price, portf_value, current_cap, ytd_close, portf_value_ytd, ccy_list = get_updated_porf_value(
                cursor, id)
            return [portf, last_price, portf_value, current_cap, ytd_close, ccy_list]
        data = request.form.get("trade").split(',')
        details = [data[0], 'sell' if data[1]
                   == 'buy' else 'buy', float(data[2])]
        return render_template("trading.html", details=details)
    else:
        cursor.execute(
            'SELECT capital, time FROM capital_history WHERE user_id = %s;', (id, ))
        cap_hist = cursor.fetchall()
        if not cap_hist:
            htmlstr = ""
            cursor.execute("INSERT INTO capital_history (user_id, capital, time) VALUES (%s, 1000000, %s);",
                           (id, datetime.now()))
            conn.commit()
        else:
            htmlstr = cap_graph(cap_hist, cursor, id, 4, 8)
            htmlstr_m = cap_graph(cap_hist, cursor, id, 2, 4.2)
            portf, last_price, portf_value, current_cap, ytd_close, portf_value_ytd, ccy_list = get_updated_porf_value(
                cursor, id)
            li = [datetime.strptime(
                i[1][:10], '%Y-%m-%d').date() for i in cap_hist]
            if (datetime.now().date() - timedelta(days=4)) in li:
                idx = li.index(datetime.now().date() - timedelta(days=4))
                cap_value_ytd = cap_hist[idx][0]
            else:
                cap_value_ytd = current_cap
        cursor.close()
        return render_template("portfo.html", p=portf, lastpx=last_price, htmlstr=htmlstr, htmlstr_m=htmlstr_m, mkt_value=portf_value, current_cap=current_cap, ytd_close=ytd_close, ytd_p_value=portf_value_ytd, ytd_cap_value=cap_value_ytd, ccy_list=ccy_list)


def get_updated_porf_value(cursor, id):
    cursor.execute(
        'SELECT * FROM portfolio WHERE user_id = %s ORDER BY id DESC', (id, ))
    portf = cursor.fetchall()
    cursor.execute(
        'SELECT capital FROM users WHERE id = %s;', (id, ))
    idle_cash = cursor.fetchall()
    if not portf:
        return [], {}, 0, idle_cash[0][0], {}, 0
    else:
        last_price = {i[1]: float("{:.2f}".format(yf.Ticker(i[1]).fast_info['lastPrice']))
                      for i in portf}
        last_price_usd = {}
        ccy_list = {}
        ytd_close_price = {i[1]: float("{:.2f}".format(yf.Ticker(i[1]).fast_info['regularMarketPreviousClose']))
                           for i in portf}
        for i in range(len(last_price)):
            ccy, fx_rate = stock.get_basic_info(
                portf[i][1])[1:] if '.' in portf[i][1] else ['$', 1]
            last_price_usd[portf[i][1]] = last_price[portf[i][1]]/fx_rate
            ccy_list[portf[i][1]] = ccy
        print(portf)
        portf_value = float(functools.reduce(lambda x, y: x+y, [last_price_usd[key]*portf[idx][6]
                                                                for idx, key in enumerate(last_price)]))
        last_portf_value = float(functools.reduce(lambda x, y: x+y, [last_price_usd[key]*portf[idx][6]
                                                                     for idx, key in enumerate(ytd_close_price)]))
        update_cap = float(idle_cash[0][0]) + portf_value
    return portf, last_price, portf_value, idle_cash[0][0], ytd_close_price, last_portf_value, ccy_list


def daily_cap_update():
    conn = try_connect(c)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users;')
    print('starting...')
    id = cursor.fetchall()
    for i in id:
        update_cap = get_updated_porf_value(cursor, i[0])[3]
        cursor.execute(
            "INSERT INTO capital_history (user_id, capital, time) VALUES (%s, %s, %s);", (i[0], update_cap, datetime.now())),
        conn.commit()
    cursor.close()
    return print('ending...')


scheduler = BackgroundScheduler(daemon=False, timezone='utc')
scheduler.add_job(daily_cap_update, 'cron',
                  day_of_week='mon-fri', hour=22, minute=0, misfire_grace_time=10)
scheduler.start()
print(threading.active_count())
print(threading.current_thread)
# print(scheduler._thread)
# print(scheduler.get_jobs())
# scheduler.shutdown()
