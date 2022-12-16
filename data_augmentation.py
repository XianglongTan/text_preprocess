import random
import re

PUNCTUATION_PATTERN = re.compile(',|，|:|：|!|！|\\?|？|;|；|、|。')

class DataAugmentor():
    '''
    1. 长句随机删除 非 label 文本短句，短句定义
        * [,|，|：|:] 分割的子句
    '''
    
    def __init__(self, prop_delete_short_sentence=0.0, prop_not_augment=1.0):
        self.prop_dict = {
            '不增强':prop_not_augment,
            '删除短句':prop_delete_short_sentence,
        }
        
    def _split_text_by_label(self, text, labels):
        '''
        e.g. 百度获得一千万 [B] a轮 [E] 融资 --> [(百度, 融资方), (获得, O), (一千万, 金额), ([B] a轮 [E] 融资, O)] 
        '''
        res = []
        labels.sort(key=lambda x: x[0])
        for i, label in enumerate(labels):
            if i == 0:
                res.append((text[:label[0]], 'O'))
                res.append((text[label[0]:label[1]], label[2]))
            elif i > 0:
                res.append((text[previous_label_end:label[0]], 'O'))
                res.append((text[label[0]:label[1]], label[2]))
                if i == len(labels) - 1:
                    res.append((text[label[1]:], 'O'))
            previous_label_end = label[1]
        return [x for x in res if len(x[0]) > 0]

    def _split_text_into_short_sentences(self, text, labels):
        short_sentences = []
        split_by_label_sentences = self._split_text_by_label(text, labels)
        return split_by_label_sentences
        
    def delete_short_sentence(self, text, labels):
        '''
        e.g. 
        origin: 思派成立于2014年，旗下拥有思派健康、远通保险经纪、思派大药房、思派医疗、比逊医疗等多家业务公司。
                思派在北京、上海、广州设立了集团总部，在56个城市建立了分支机构。目前全职员工95%拥有医、药、护理、保险、金融教育背景和工作经验。
                在全体员工中，硕士学历86人，博士学历8人。
        aug: 思派成立于2014年，旗下拥有思派健康、远通保险经纪、思派大药房、思派医疗、比逊医疗等多家业务公司。
             思派在北京、上海、广州设立了集团总部，目前全职员工95%拥有医、药、护理、保险、金融教育背景和工作经验。
             在全体员工中，硕士学历86人，博士学历8人。
        '''
        short_sentences = self._split_text_into_short_sentences(text, labels)
        if len(short_sentences) == 1:
            return text, labels
        label_start, new_text, new_labels = 0, '', []
        for i, sentence in enumerate(short_sentences):
            s_text, s_label = sentence[0], sentence[1]
            if s_label != 'O':
                label_start = len(new_text)
                label_end = label_start + len(s_text)
                new_labels.append([label_start, label_end, s_label])
                new_text += s_text
            else:
                if len(s_text) <= 4:
                    new_text += s_text 
                    continue
                punc_split_s_texts = PUNCTUATION_PATTERN.split(s_text)
                if len([x for x in punc_split_s_texts if len(x) > 0]) <= 1 or len(punc_split_s_texts) <= 3:
                    new_text += s_text
                else:
                    for sid, punc_split_s_text in enumerate(punc_split_s_texts):
                        if len(punc_split_s_text) == 0:
                            new_text += '，'
                        elif ((sid < len(punc_split_s_texts) -1) and (sid > 0))\
                                and random.random() < self.prop_dict['删除短句']:
                            continue
                        elif sid == len(punc_split_s_texts) -1:
                            new_text += punc_split_s_text 
                        else:
                            new_text += punc_split_s_text + '，'
            # print(new_text, '  |  ',s_text)
        return new_text, new_labels

    def augment(self, text, labels, num_aug):
        '''
        Argument
        --------
        text: str
        labels: List[ List[ start_position, end_position, label_type ] ]
        num_aug: int

        Return
        --------
        res: List[ Dict{'text': str, 'labels': List[ List[ start_position, end_position, label_type ] ] } ]
        '''   
        res = []
        labels.sort(key=lambda x: x[0])
        if len(labels) == 0:
            return [{'text':text, 'labels':labels}]
        while len(res) < num_aug:
            if random.random() < self.prop_dict['不增强']:
                res.append({'text': text, 'labels': labels})
                continue
            aug_text, aug_labels = text, labels.copy()
            aug_text, aug_labels = self.delete_short_sentence(aug_text, aug_labels)
            res.append({'text': aug_text, 'labels': aug_labels})
        return res