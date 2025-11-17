import re
from datetime import datetime
from typing import NamedTuple

import requests
from bs4 import BeautifulSoup

BASE_URL = 'https://mail.openjdk.org/pipermail'


class Checkpoint(NamedTuple):
    month: str
    id: str


class MonthMail(NamedTuple):
    month_url: str
    mail_url: str


class Mail(NamedTuple):
    list: str
    month: str
    id: str
    subject: str
    author: str
    email: str
    date: str
    body: str


def http_session(concurrency_limit):
    a = requests.adapters.HTTPAdapter(pool_connections=concurrency_limit, pool_maxsize=concurrency_limit)
    session = requests.session()
    session.mount("https://", a)
    session.headers = {
        'user-agent': 'Mozilla'
    }
    return session


class MailingList:
    def __init__(self, session, name, checkpoint):
        self.name = name
        self.checkpoint = checkpoint
        self.url = f'{BASE_URL}/{name}'
        self.session = session

    def mail_urls(self):
        checkpoint_month_url = f'{self.url}/{self.checkpoint.month}/date.html'
        checkpoint_id_url = f'{self.url}/{self.checkpoint.month}/{self.checkpoint.id}.html'
        month_urls = self.fetch_month_urls()
        try:
            i = month_urls.index(checkpoint_month_url)
            month_urls = month_urls[:i + 1]
        except ValueError:
            ...
        for month_url in reversed(month_urls):
            mail_urls = self.fetch_mail_urls(month_url)
            if month_url == checkpoint_month_url:
                i = mail_urls.index(checkpoint_id_url)
                mail_urls = mail_urls[i + 1:]
            yield from mail_urls

    def fetch_html_page(self, url):
        with self.session.get(url) as response:
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")

    @staticmethod
    def convert_date(s):
        dt = datetime.strptime(s, "%a %b %d %H:%M:%S %Z %Y")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def fetch_mail(self, url):
        m = re.match(r'.*/([^/]+)/([^/]+)/([^/]+).html', url)
        list = m.group(1)
        month = m.group(2)
        id = m.group(3)
        page = self.fetch_html_page(url)
        subject = page.select_one('h1').get_text().strip()
        author = page.select_one('b').get_text().strip()
        email = page.select_one('a').get_text().replace(' at ', '@').strip()
        date = MailingList.convert_date(page.select_one('i').get_text().strip())
        pre = page.select_one('pre')
        body = pre.get_text() if pre else ''  # absent body observed
        if not re.sub(r'[^\w+#]+', '', author):  # author key has been observed to be '-' and '- -'
            author = email
        return Mail(list=list, month=month, id=id, subject=subject, author=author, email=email, date=date, body=body)

    def fetch_month_urls(self):
        page = self.fetch_html_page(f'{self.url}/')
        return [f'{self.url}/{a["href"]}' for a in page.find_all("a", string="[ Date ]")]

    def fetch_mail_urls(self, month_url):
        page = self.fetch_html_page(month_url)
        regex_link = re.compile(r'[0-9]+.html')
        regex_trail = re.compile(r'[^/]+.html')
        return [regex_trail.sub(a['href'], month_url) for a in page.find_all("a", href=regex_link)]
