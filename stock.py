# all the functions are add-on to yfinance to have a more comprehensive dataset.
import yfinance as yf
from yahooquery import Ticker
from flask import flash
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import time
import pandas as pd
from datetime import datetime


def get_basic_info(ticker):
    raw = Ticker(ticker).summary_detail[ticker]
    ccy = yf.Ticker(ticker).info['currency']
    if ccy == 'USD':
        return raw, '$', 1
    else:
        fx_rate = yf.Ticker(ccy+'=X').fast_info['lastPrice']
        print(ccy, fx_rate)
        ccy = '¥' if ccy.upper() == 'JPY' else '£' if ccy.upper(
        ) == 'GBP' else '€' if ccy.upper() == 'EUR' else 'HK$' if ccy.upper() == 'HKD' else '$'
    # keys = ['previousClose', 'open', 'dayLow', 'dayHigh', 'beta', 'forwardPE', 'volume', 'averageVolume', 'bid', 'ask', 'bidSize', 'askSize', 'marketCap', 'fiftyTwoWeekLow', 'fiftyTwoWeekHigh']
    # data = [raw[key] for key in keys]
        return raw, ccy, fx_rate


def get_yf_data(metatable, need_yf, ticker):
    name = yf.Ticker(ticker)
    yf_fail_data = []
    for data in need_yf:
        try:
            if data == 'Income Statement':
                df = name.income_stmt.iloc[::-1]
                df.rename(columns=lambda x: str(x)[:10], inplace=True)
                metatable.append(df.map(convert_numdata_fs))
            elif data == 'Balance Sheet':
                df = name.balance_sheet.iloc[::-1]
                df.rename(columns=lambda x: str(x)[:10], inplace=True)
                metatable.append(df.map(convert_numdata_fs))
            elif data == 'Cash Flow Statement':
                df = name.cash_flow.iloc[::-1]
                df.rename(columns=lambda x: str(x)[:10], inplace=True)
                metatable.append(df.map(convert_numdata_fs))
            elif data == 'Corporate Holders':
                df = name.institutional_holders
                df.rename(columns={"pctHeld": "% Held"}, inplace=True)
                metatable.append(df.map(convert_numdata_corp))
            elif data == 'Corporate Actions':
                df = name.actions.tail(20).iloc[::-1]
                df = df.reindex([str(i)[:10] for i in df.index])
                metatable.append(df.map(lambda x: '-' if x == 0 else x))
            elif data == 'Insider Actions':
                df = name.insider_transactions.head(20)
                df.rename(columns={"Text": "Details",
                          "Start Date": "Date"}, inplace=True)
                df.drop(columns=['URL', 'Transaction',
                        'Ownership'], inplace=True)
                metatable.append(df.map(convert_numdata_corp))
        except:
            yf_fail_data.append(data)
            flash(
                f'Data for {data.lower()} is currently unavailable for {ticker}.')
    return metatable, yf_fail_data


def convert_numdata_corp(num):
    if type(num) == float:
        return str("{:.2f}".format(num))
    try:
        if num / 1000000000 > 1:
            num = str("{:.1f}".format(num / 1000000000))+'B'
        elif num / 1000000 > 1:
            num = str("{:.1f}".format(num / 1000000))+'M'
        elif num / 1000 > 1:
            num = str("{:.1f}".format(num / 1000))+'K'
        return num
    except:
        return num


def convert_numdata_fs(num):
    if str(num)[-2:] == '.0':
        if abs(num / 1000000000) > 1:
            num = str("{:.1f}".format(num / 1000000000))+'B'
        elif abs(num / 1000000) > 1:
            num = str("{:.1f}".format(num / 1000000))+'M'
        elif abs(num / 1000) > 1:
            num = str("{:.1f}".format(num / 1000))+'K'
    elif 'nan' in str(num):
        num = 'N/A'
    return num


def convert_strdata(data):
    for item in data:
        for idx, number in enumerate(item):
            number = number.strip()
            if 'T' in number:
                value_num = number.rstrip(number[-1])
                item[idx] = float(value_num)*1000000000000
            elif 'B' in number:
                value_num = number.rstrip(number[-1])
                item[idx] = float(value_num)*1000000000
            elif 'M' in number:
                value_num = number.rstrip(number[-1])
                item[idx] = float(value_num)*1000000
            elif 'K' in number:
                print(number)
                value_num = number.rstrip(number[-1])
                item[idx] = float(value_num)*1000
            else:
                try:
                    item[idx] = float(number)
                except:
                    item[idx] = 'N/A'
    return data


def to_stat_page(browser, url):
    try:
        btn = browser.find_element(
            By.XPATH, '//a[@href="'+url+'key-statistics/"]')
        btn.send_keys(Keys.RETURN)
    except Exception as e:
        print(e)


def to_news_page(browser, url):
    time.sleep(1)
    btn = browser.find_element(By.XPATH, '//a[@href="'+url+'news/"]')
    btn.send_keys(Keys.RETURN)
    time.sleep(1)


def to_summary_page(browser, url):
    btn = browser.find_element(By.XPATH, '//a[@href="'+url+'"]')
    btn.send_keys(Keys.RETURN)


def to_analysis_page(browser, url):
    btn = browser.find_element(By.XPATH, '//a[@href="'+url+'analysis/"]')
    btn.send_keys(Keys.RETURN)


def scroll_down(self):
    i = 0
    # Get scroll height.
    last_height = self.execute_script("return document.body.scrollHeight")
    while True:
        i += 1
        if i == 4:
            break
        else:
            # Scroll down to the bottom.
            self.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            # Calculate new scroll height and compare with last scroll height.
            new_height = self.execute_script(
                "return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height


def get_valuation_metrics(browser, url, ticker, i) -> pd.DataFrame:
    try:
        print(i)
        if i == 3:
            return []
        full_url = 'https://finance.yahoo.com' + url + 'key-statistics/'
        if browser.current_url != full_url:
            to_stat_page(browser, url)
        metadata = []
        metaheader = []
        for table in browser.find_elements(By.XPATH, "//table[@class='table yf-104jbnt']//tr"):
            data = [item.text for item in table.find_elements(
                By.XPATH, ".//*[self::td]")]
            header = [item.text for item in table.find_elements(
                By.XPATH, ".//*[self::th]")]
            metadata.append(data)
            if header != []:
                metaheader.append(header)
        metadata = [data for data in metadata if data != []]
        row = list(zip(*metadata))[0]
        for item in metadata:
            del item[0]
        metaheader = list(filter(None, metaheader[0]))
        pd.set_option('display.float_format', lambda x: '%.2f' % x)
        valuation_table = pd.DataFrame(metadata, index=row, columns=metaheader)
        cols = valuation_table.columns.values
        for i in range(len(cols) - 1):
            cols[i + 1] = datetime.strptime(
                cols[i + 1], '%m/%d/%Y').strftime('%Y-%m-%d')
            valuation_table.columns.values[i] = cols[i]
        print(valuation_table)
        return valuation_table
    except Exception as e:
        print(e.args)
        i += 1
        get_valuation_metrics(browser, url, ticker, i)


def get_financial_ratio(browser, url, ticker, i) -> pd.DataFrame:
    try:
        print(i)
        if i == 3:
            return []
        full_url = 'https://finance.yahoo.com' + url + 'key-statistics/'
        if browser.current_url != full_url:
            to_stat_page(browser, url)
        metadata = []
        metaheader = []
        fin_sum_section = browser.find_elements(
            By.XPATH, "//section[@class='yf-14j5zka']")
        for table in fin_sum_section[0].find_elements(By.XPATH, ".//*[self::tr]"):
            *header, data = table.text.split()
            header = ' '.join(header)
            metadata.append(data)
            metaheader.append(header)
        finance_summary = pd.Series(dict(
            (name, value) for name, value in list(zip(metaheader, metadata)))).to_frame()
        finance_summary = finance_summary.assign(k="--")
        finance_summary = finance_summary.set_axis(
            [ticker, ' '], axis='columns')
        print(finance_summary)
        return finance_summary
    except Exception as e:
        print(e.args)
        i += 1
        get_financial_ratio(browser, url, ticker, i)


def get_trading_information(browser, url, ticker, i) -> pd.DataFrame:
    try:
        print(i)
        if i == 3:
            return []
        full_url = 'https://finance.yahoo.com' + url + 'key-statistics/'
        if browser.current_url != full_url:
            to_stat_page(browser, url)
        metadata = []
        metaheader = []
        fin_sum_section = browser.find_elements(
            By.XPATH, "//section[@class='yf-14j5zka']")
        for table in fin_sum_section[1].find_elements(By.XPATH, ".//*[self::tr]"):
            *header, data = table.text.split()
            header = ' '.join(header)
            try:
                int(header[-1])
                header = header[:-1]
                header = header.strip()
            except:
                continue
            metadata.append(data)
            metaheader.append(header)
        share_stat = pd.Series(
            dict((name, value) for name, value in list(zip(metaheader, metadata)))).to_frame()
        share_stat = share_stat.assign(k="--")
        share_stat = share_stat.set_axis([ticker, ' '], axis='columns')
        return share_stat
    except Exception as e:
        print(e.args)
        i += 1
        get_financial_ratio(browser, url, ticker, i)


news_website = ['Bloomberg', 'Reuters', 'Investopedia', 'The Telegraph', 'The Wall Street Journal',
                'Barrons.com', 'Fortune', 'Retail Dive', 'WSJ', 'Yahoo Finance']


# news with only a few trusted source, and a separate column for official press release
def get_news(browser, url) -> list:
    full_url = 'https://finance.yahoo.com' + url + 'news/'
    if browser.current_url != full_url:
        to_news_page(browser, url)
    btn = browser.find_element(By.ID, "tab-latest-news")
    btn.send_keys(Keys.RETURN)
    scroll_down(browser)
    test = browser.find_elements(
        By.XPATH, "//section[@data-testid='storyitem']")
    metaheader = []
    metadata = []
    metalink = []
    for idx in range(len(test)):
        header = test[idx].find_element(By.XPATH, ".//*[self::h3]").text
        src = [i.strip() for i in test[idx].find_elements(
            By.XPATH, ".//*[self::div]")[-1].text.split(sep='•')]
        link = test[idx].find_element(
            By.XPATH, ".//*[self::a]").get_attribute('href')
        if src[0] in news_website:
            metaheader.append(header)
            metadata.append(src)
            metalink.append(link)
    news_data = list(zip(metaheader, metadata, metalink))
    return news_data


def get_press_release(browser, url) -> list:
    to_remove = ['Zacks Small Cap Research']
    full_url = 'https://finance.yahoo.com' + url + 'news/'
    if browser.current_url != full_url:
        to_news_page(browser, url)
    btn = browser.find_element(By.ID, "tab-press-releases")
    btn.send_keys(Keys.RETURN)
    time.sleep(1)
    test = browser.find_elements(
        By.XPATH, "//section[@data-testid='storyitem']")
    metaheader = []
    metadata = []
    metalink = []
    for idx in range(len(test)):
        header = test[idx].find_element(By.XPATH, ".//*[self::h3]").text
        src = [i.strip() for i in test[idx].find_elements(
            By.XPATH, ".//*[self::div]")[-1].text.split(sep='•')]
        if src in to_remove:
            continue
        link = test[idx].find_element(
            By.XPATH, ".//*[self::a]").get_attribute('href')
        metaheader.append(header)
        metadata.append(src)
        metalink.append(link)
    pr_data = list(zip(metaheader, metadata, metalink))
    return pr_data


def get_sec_filing(browser, url) -> list:
    full_url = 'https://finance.yahoo.com' + url + 'news/'
    if browser.current_url != full_url:
        to_news_page(browser, url)
    btn = browser.find_element(By.ID, "tab-sec-filing")
    btn.send_keys(Keys.ENTER)
    element = browser.find_element(
        By.XPATH, value='//*[contains(text(), "All SEC Filings")]')
    element.send_keys(Keys.RETURN)
    sec_filing = browser.find_elements(
        By.XPATH, "//div[@class='sec-story-container svelte-nhb3xj']")
    metalink = []
    metaheader = []
    metadate = []
    for idx in range(len(sec_filing)):
        sec_filing = browser.find_elements(
            By.XPATH, "//div[@class='sec-story-container svelte-nhb3xj']")
        # WebDriverWait(browser, 10).until(EC.element_to_be_clickable((By.XPATH, ".//*[self::a]")))
        if sec_filing[idx].text[0] == '1':
            element = sec_filing[idx].find_element(By.XPATH, ".//*[self::a]")
            header = sec_filing[idx].find_element(
                By.XPATH, ".//*[self::h3]").text
            metaheader.append(header)
            filing_date = sec_filing[idx].find_elements(
                By.XPATH, ".//div//*[self::div]")[1].text
            metadate.append(filing_date.strip())
            element.send_keys(Keys.RETURN)
            time.sleep(2)
            try:
                link = browser.find_element(
                    By.XPATH, "//a[@class='Bgc($linkColor) Bgc($linkActiveColor):h Fz(s) Cur(p) Fw(500) Py(8px) Px(10px) C(white) Bd(0) Bdc($linkColor) Bdrs(18px) Miw(120px) Va(t) D(ib) Ta(c) Td(n)']")
                metalink.append(link.get_attribute('href'))
            except:
                metalink.append('')
                flash(
                    f'Downloadable link for {header} on {filing_date.strip()} is unavailable.')
            browser.back()
            time.sleep(1)
    sec_data = list(zip(metaheader, metadate, metalink))
    return sec_data


def get_competitors(browser, url) -> pd.DataFrame:
    full_url = 'https://finance.yahoo.com' + url
    if browser.current_url != full_url:
        to_summary_page(browser, url)
    compare_to_section = browser.find_elements(
        By.XPATH, "//section[@data-testid='compare-to']//section")
    metadata = []
    metaname = []
    column = ['Price', '1D % Change']
    for idx in range(len(compare_to_section)):
        ticker_element = compare_to_section[idx].find_elements(
            By.XPATH, ".//*[self::span]")
        name_element = compare_to_section[idx].find_elements(
            By.XPATH, ".//*[self::div[@class='longName yf-15b2o7n']]")
        stock_ticker = [i.text for i in ticker_element]
        stock_name = [i.text for i in name_element]
        metadata.append(stock_ticker[:3])
        metaname.append(stock_name)
    row = [
        f'{metadata[i][0]} - {metaname[i][0]}' for i in range(len(metadata))]
    metadata = [metadata[i][1:] for i in range(len(metadata))]
    competitors = pd.DataFrame(metadata, index=row, columns=column)
    return competitors


def get_performance_vs_market(browser, url) -> pd.DataFrame:
    full_url = 'https://finance.yahoo.com' + url + 'news/'
    if browser.current_url != full_url:
        to_news_page(browser, url)
    time.sleep(2)
    perf_overview_section = browser.find_elements(
        By.XPATH, "//section[@data-testid='performance-overview-on-news']//table")
    print(perf_overview_section)
    time.sleep(2)
    column = [item.text for item in perf_overview_section[0].find_elements(
        By.XPATH, ".//*[self::th]")]
    column = column[1:]
    metadata = []
    for i in perf_overview_section[0].find_elements(By.XPATH, ".//*[self::tr]"):
        data = [item.text for item in i.find_elements(
            By.XPATH, ".//*[self::td]")]
        print(data)
        metadata.append(data)
    row = [metadata[i][0] for i in range(len(metadata))]
    metadata = [metadata[i][1:] for i in range(len(metadata))]
    perf_overview_table = pd.DataFrame(metadata, index=row, columns=column)
    return perf_overview_table


def data_to_df(section) -> pd.DataFrame:
    column = [item.text for item in section.find_elements(
        By.XPATH, ".//*[self::th]")]
    column = column[1:]
    metadata = []
    for i in section.find_elements(By.XPATH, ".//*[self::tr]"):
        data = [item.text for item in i.find_elements(
            By.XPATH, ".//*[self::td]")]
        metadata.append(data)
    metadata = [data for data in metadata if data != []]
    row = [metadata[i][0] for i in range(len(metadata))]
    metadata = [metadata[i][1:] for i in range(len(metadata))]
    df = pd.DataFrame(metadata, index=row, columns=column)
    return df


def get_rev_est(browser, url) -> pd.DataFrame:
    rev_est_section = browser.find_element(
        By.XPATH, "//section[@data-testid='revenueEstimate']//table")
    rev_est = data_to_df(rev_est_section)
    return rev_est


def get_estimates(browser, url, ticker, i):
    try:
        print(i)
        if i == 3:
            return []
        to_analysis_page(browser, url)
        df1 = get_rev_est(browser, url)
        df2 = get_earnings_est(browser, url)
        df3 = get_earnings_hist(browser, url)
        df4 = get_growth_est(browser, url)
        df5 = get_eps_trend(browser, url)
        return df1, df2, df3, df4, df5
    except Exception as e:
        i += 1
        print(e)
        get_estimates(browser, url, ticker, i)


def get_rev_est(browser, url) -> pd.DataFrame:
    rev_est_section = browser.find_element(
        By.XPATH, "//section[@data-testid='revenueEstimate']//table")
    rev_est = data_to_df(rev_est_section)
    print('rev_est ok')
    return rev_est


def get_earnings_est(browser, url) -> pd.DataFrame:
    earnings_est_section = browser.find_element(
        By.XPATH, "//section[@data-testid='earningsEstimate']//table")
    earnings_est = data_to_df(earnings_est_section)
    print('earnings_est ok')
    return earnings_est


def get_earnings_hist(browser, url) -> pd.DataFrame:
    earnings_hist_section = browser.find_element(
        By.XPATH, "//section[@data-testid='earningsHistory']//table")
    earnings_hist = data_to_df(earnings_hist_section)
    print('earnings_hist ok')
    return earnings_hist


def get_growth_est(browser, url) -> pd.DataFrame:
    growth_est_section = browser.find_element(
        By.XPATH, "//section[@data-testid='growthEstimate']//table")
    growth_est = data_to_df(growth_est_section)
    print('growth_est ok')
    return growth_est


def get_eps_trend(browser, url) -> pd.DataFrame:
    eps_section = browser.find_element(
        By.XPATH, "//section[@data-testid='epsTrend']//table")
    eps_trend = data_to_df(eps_section)
    print('eps_trend ok')
    return eps_trend
