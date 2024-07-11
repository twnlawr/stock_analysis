# pip install fuzzywuzzy, python-levenshtein
from flask import Flask, render_template, request, flash, redirect, session
from flask_session import Session
from datetime import datetime
import requests
from werkzeug.security import check_password_hash, generate_password_hash
from cs50 import SQL
from functools import wraps
import stock
import yfinance as yf
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import pandas as pd
import re
import plotly.graph_objs as go
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


db = SQL("sqlite:///history.db")
need_selenium_list = ['Financial Ratio', 'Estimates', 'Competitors', 'Performance vs Market', 'Valuation Metrics',
                      'SEC Filings', 'Trading Information', 'Press Release', 'News']


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
    chrome_browser = webdriver.Chrome(options=chrome_options)
    safari_options = webdriver.SafariOptions()
    safari_options.add_argument('--ignore-ssl-errors=yes')
    safari_options.add_argument('--ignore-certificate-errors')
    # safari_browser = webdriver.Safari(keep_alive=False, options=safari_options)
    chrome_browser.maximize_window()
    chrome_browser.get('https://finance.yahoo.com/quote/'+stock+'/')
    return chrome_browser

# to improve: change competitors df on % change & name of competitors, multiple stocks


@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        try:
            id = session.get("user_id")
            # get the stocks and data in separate list
            stocks = request.form.get("stocks").lstrip().split(sep=' ')
            # will be used when multiple stocks are available
            stocks = [name.upper() for name in stocks]
            with open('stocks.csv', 'r') as stock_name_file:
                ticker_list = stock_name_file.read().split(sep=',')
            if not set(stocks).issubset(ticker_list):
                flash("Invalid ticker(s).")
                return redirect("/")
            request_data = request.form.getlist("data")
            if not request_data:
                flash("Please select the data you wish to analyze.")
                return redirect("/")
            need_selenium = [
                i for i in request_data if i in need_selenium_list]
            need_yf = [i for i in request_data if i not in need_selenium_list]
            metatable, news_data, pr_data, sec_data, est_data, est_name = [], [], [], [], [], []
            fig = pd.DataFrame()
            for ticker in stocks:
                if 'Historical Data' in need_yf:
                    start_date = request.form.get("start_date")
                    end_date = request.form.get("end_date")
                    stocks_for_yf_trade_history = request.form.get("stocks")
                    date_check = re.compile(
                        r'^(?:(?:31(-)(?:0?[13578]|1[02]))\1|(?:(?:29|30)(-)(?:0?[13-9]|1[0-2])\2))(?:(?:1[6-9]|[2-9]\d)?\d{2})$|^(?:29(-)0?2\3(?:(?:(?:1[6-9]|[2-9]\d)?(?:0[48]|[2468][048]|[13579][26])|(?:(?:16|[2468][048]|[3579][26])00))))$|^(?:0?[1-9]|1\d|2[0-8])(-)(?:(?:0?[1-9])|(?:1[0-2]))\4(?:(?:1[8-9]\d{2}|20[0-2][1-9]))$')
                    if not (start_date and end_date):
                        flash("Please input start date and end date.")
                        return redirect("/")
                    else:
                        try:
                            chk_start_date = datetime.strptime(
                                start_date, "%d-%m-%Y").date()
                            chk_end_date = datetime.strptime(
                                end_date, "%d-%m-%Y").date()
                        except:
                            flash("Please input dates in DD-MM-YYYY.")
                            return redirect("/")
                        try:
                            start_match = re.search(
                                date_check, start_date).string
                            end_match = re.search(date_check, end_date).string
                        except:
                            flash("Error in parsing dates. Please try again.")
                            return redirect("/")
                        if not start_match or not end_match:
                            flash("Please input a valid date.")
                            return redirect("/")
                        if chk_end_date <= chk_start_date:
                            flash(
                                "Start date cannot be larger than / equal to end date!")
                            return redirect("/")
                        if chk_start_date >= datetime.now().date():
                            flash("Invalid start date.")
                            return redirect("/")
                        else:
                            # switch d-m-y to y-m-d coz dunno how to change regex code...
                            k = start_date.split('-')
                            start_date = k[2] + '-' + k[1] + '-' + k[0]
                            k = end_date.split('-')
                            end_date = k[2] + '-' + k[1] + '-' + k[0]
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
                            item = "get_" + item.replace(" ", "_").lower()
                            # to call the respective function
                            data = getattr(stock, f'{item}')
                            table = data(browser, url)
                            # for Estimates only, take all 5 df and append to metatable
                            if type(table) == tuple:
                                est_name = ['Revenue Estimate', 'Earnings Estimate',
                                            'Earnings History', 'Growth Estimate', 'EPS Trend']
                                for idx in range(len(table)):
                                    est_data.append(table[idx])
                                    # to ensure len(metatable) == len(data_id_name) for html to render
                                metatable.append(pd.DataFrame())
                            else:
                                metatable.append(table)
                    browser.close()
                if 'Historical Data' in need_yf:
                    trade_history = yf.download(
                        stocks_for_yf_trade_history, start=start_date, end=end_date, group_by="ticker")
                    metatable.append(trade_history)
                    fig = go.Figure(data=[go.Candlestick(x=trade_history.index, open=trade_history['Open'],
                                    high=trade_history['High'], low=trade_history['Low'], close=trade_history['Close'], name='Stock Data')])
                    fig.update_layout(
                        yaxis_title='Stock Price (USD)', xaxis_title='Date')
            db.execute("INSERT INTO search_history (user_id, s_comp, s_content, time) VALUES (?, ?, ?, ?)",
                       id, ', '.join(stocks), ', '.join(request_data), datetime.now())
            data_id_name = [item.replace(" ", "_").lower()
                            for item in request_data]
            return render_template("results.html", all_table=[table.to_html(classes='table table-stripped table-hover table-responsive') for table in metatable], est=[estimates.to_html(classes='table table-stripped') for estimates in est_data], est_no=range(len(est_name)), est_name=est_name, news=news_data, pr=pr_data, sec=sec_data, name=request_data, id_name=data_id_name, number=range(len(request_data)), fig=fig.to_html())
        except:
            flash('Something went wrong. Please try again.')
            return redirect("/")
    else:
        return render_template("index.html")


@app.route('/history', methods=['GET', 'POST'])
@login_required
def history():
    id = session.get("user_id")
    if request.method == 'POST':
        btn = request.form.get('button')
    else:
        history = db.execute(
            'SELECT * FROM search_history WHERE user_id = ? ORDER BY id DESC', id)
        print(history)
        return render_template('history.html', history=history)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        pw = request.form.get("pw")
        check = request.form.get("check")
        registrants = db.execute("SELECT username FROM users")
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
            if username == i['username']:
                flash("This username has been taken.")
                return render_template("register.html")
        else:
            db.execute("INSERT INTO  users (username, pw) VALUES (?, ?)",
                       username, generate_password_hash(pw))
            return redirect('/')
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()
    if request.method == "POST":
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          request.form.get("username"))
        if len(rows) != 1 or not check_password_hash(rows[0]["pw"], request.form.get("password")):
            flash("Wrong username or password")
            return render_template("login.html")
        session["user_id"] = rows[0]["id"]
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
        id = session.get("user_id")
        db.execute("DELETE FROM search_history WHERE user_id = ?", id)
        db.execute("DELETE FROM users WHERE id = ?", id)
        session.clear()
        flash("Account deleted")
        return redirect("/")
    else:
        return render_template("delete_account.html")


@app.route("/delete_history", methods=['GET', 'POST'])
@login_required
def delete_history():
    if request.method == 'POST':
        id = session.get("user_id")
        db.execute("DELETE FROM search_history WHERE user_id = ?", id)
        flash("History deleted")
        return redirect("/")
    else:
        return render_template("delete_history.html")


@app.route("/change_pw", methods=["GET", "POST"])
@login_required
def change_pw():
    if request.method == 'POST':
        id = session.get("user_id")
        username = db.execute("SELECT username FROM users WHERE id = ?", id)
        username = username[0]['username']
        new_pw = request.form.get("new_pw")
        new_check = request.form.get("new_check")
        if new_pw == "" or new_check == "":
            flash("Password cannot be blank")
            return render_template("change_pw.html")
        elif new_pw != new_check:
            flash("Passwords do not match")
            return render_template("change_pw.html")
        else:
            old_pw = db.execute("SELECT pw FROM users WHERE id = ?", id)
            if check_password_hash(old_pw[0]['pw'], new_pw):
                flash("Please select a new password")
                return render_template("change_pw.html")
            elif new_pw == username:
                flash("Password cannot be same as username")
                return render_template("change_pw.html")
            else:
                db.execute("UPDATE users SET pw = ? WHERE id = ?",
                           generate_password_hash(new_pw), id)
                flash("Password changed")
                return redirect("/")
    else:
        return render_template("change_pw.html")
