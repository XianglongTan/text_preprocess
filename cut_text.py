import re

def cut_short_text(text:str, max_len:int=256):
    '''
    按标点和空格分成短文本
    '''
    p = re.compile('，|。|；|！|？|,|：|([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])|(A-Za-z)\.')
    texts = p.split(text)
    if len(texts) <= 0:
        raise Exception("text is empty")
    res = []
    for t in texts:
        if t is None:
            continue
        res.append(t[:max_len])
    return res