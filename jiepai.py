import requests
import json
import re
import os
import pymongo
from urllib.parse import urlencode
from requests.exceptions import RequestException
from multiprocessing import Pool
from bs4 import BeautifulSoup
from hashlib import md5
from json.decoder import JSONDecodeError

from config import *

client = pymongo.MongoClient(MONGO_URL, connect = False)
db = client[MONGO_DB]

def get_page_index(offset, keyword):
    data = {
        'offset': offset,
        'format': 'json',
        'keyword': keyword,
        'autoload': 'true',
        'count': '20',
        'cur_tab': 3,
        'from': 'gallery'
    }
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36'
    }
    url = 'https://www.toutiao.com/search_content/?' + urlencode(data)
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return None
    except RequestException:
        print('请求索引页错误')
        return None

def parse_page_index(html):
    try:
        data = json.loads(html)
        if data and 'data' in data.keys():
            for item in data.get('data'):
                yield item.get('article_url')
    except JSONDecodeError:
        pass

def get_page_detail(url):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return None
    except RequestException:
        print('请求详情页错误', url)
        return None

def parse_page_detail(html, url):
    soup = BeautifulSoup(html, 'lxml')
    title = soup.select('title')[0].get_text()
    print(title)
    images_pattern = re.compile('gallery: JSON.parse\((.*?)\),', re.S)
    result = re.search(images_pattern, html)
    if result:
        s = json.loads(result.group(1))
        data = json.loads(s)
        if data and 'sub_images' in data.keys():
            sub_images = data.get('sub_images')
            images = [item.get('url') for item in sub_images]
            for image in images:
                download_image(image)
            return {
                'title': title,
                'url': url,
                'images': images
            }

def save_to_mongo(result):
    db_datas = db[MONGO_TABLE].find({'url': {'$regex': '.*?'}})
    for db_data in db_datas:
        url = db_data['url']
        if not hasattr(result, 'get'):
            return False
        elif url == result.get('url'):
            print('数据库已有该数据，不反复存储')
            return False
    db[MONGO_TABLE].insert(result)
    print('存储到MongoDB成功', result)
    return True

def download_image(url):
    print('正在下载', url)
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            save_image(response.content)
        return None
    except RequestException:
        print('请求图片错误', url)
        return None

def save_image(content):
    file_path = '{0}/{1}/{2}.{3}'.format(os.getcwd(), 'images', md5(content).hexdigest(), 'jpg')
    if os.path.exists(file_path):
        print('图片已存在，不再保存')
    elif not os.path.exists(file_path):
        with open(file_path, 'wb') as f:
            f.write(content)
            f.close()

def main(offset):
    html = get_page_index(offset, KEYWORD)
    for url in parse_page_index(html):
        html = get_page_detail(url)
        if html:
            result = parse_page_detail(html, url)
            save_to_mongo(result)

if __name__ == '__main__':
    groups = [x * 20 for x in range(GROUP_START, GROUP_END + 1)]
    pool = Pool()
    pool.map(main, groups)
    print('共有%d条数据存入数据库' % db[MONGO_TABLE].count())
