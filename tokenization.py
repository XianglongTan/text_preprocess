import re

UNK_TOKEN = 100
zhPattern = re.compile(u'[\u4e00-\u9fa5]+')
engPattern = re.compile(u'[a-zA-Z]')
cutPattern = re.compile('##')


def has_chinese(text):
    if zhPattern.search(text):
        return True
    return False


def has_english(text):
    if engPattern.search(text):
        return True
    return False


def has_cut(text):
    if (cutPattern.search(text) or engPattern.search(text)) and '[UNK]' not in text:
        return True
    return False


def clean_text(text):
    text = text.replace('[B]', ' [B] ')
    text = text.replace('[E]', ' [E] ')
    text = text.replace('[UNK]', ' ')
    text = text.replace('##', '')
    return text


def postprocess_pred_v1(pred, win=3):
    '''
    Refine the prediction.
    1. A sequence with minor different label type will be modified to the major label type.
        e.g. B_融资方 I_融资方 I_融资方 O I_融资方 I_融资方 --> B_融资方 I_融资方 I_融资方 I_融资方 I_融资方 I_融资方

    Argument:
    --------
    win: int
        Length of window to scan the sequence
    '''
    pointer, res= 0, []
    while pointer < len(pred):
        if pred[pointer][0] in ['O', 'I']: # I 需要 B 触发才算实体一部分，否则算 O
            pointer += 1
            res.append('O')
        else:
            tmp_seq, tmp_pointer = [], pointer
            while tmp_pointer < len(pred):
                tmp_seq.append(pred[tmp_pointer])
                if tmp_pointer + 1 >= len(pred) or pred[tmp_pointer+1][0] == 'B': # 下个 token 为 B 表示实体序列中断
                    break
                if pred[tmp_pointer][0] not in ['I', 'B']: # 某个 token 后 win 窗口中 O 多于一定比例则任务实体序列中断，否则将 O 视为该实体序列一部分
                    next_win_p = [x[0] for x in pred[tmp_pointer+1:tmp_pointer+win+1]]
                    if (next_win_p.count('O') >= 0.5 * win) and next_win_p[0]:
                        break
                tmp_pointer += 1
            tmp_seq_label = []
            for x in tmp_seq:
                if x == 'O':
                    tmp_seq_label.append(x)
                else:
                    tmp_seq_label.append(x[2:])
            while tmp_seq_label[-1] == 'O':
                del tmp_seq_label[-1]
            major_label = max(tmp_seq_label, key=tmp_seq_label.count) # 取最主流 label 作为序列的实体类别，若没有主流 label 则视为 O
            if tmp_seq_label.count(major_label) > 0.5 * len(tmp_seq_label):
                tmp_res = ['B_'+major_label] + ['I_'+major_label]*(len(tmp_seq_label)-1)
            else:
                tmp_res = ['O']*len(tmp_seq_label)
            res.extend(tmp_res)
            pointer += len(tmp_res)
    assert len(res) == len(pred)
    return res


def transform_sequence_to_text(sequence:str, text:str, tokenizer):
    '''
    将 token sequence 原文(text)

    text: 原始文本
    seq_text: 保存还原文本
    eng_text: 暂存 ## 文本，直到英文文本完整再加入 seq_text

    loop 每个 token：
        a. 若是 UNK，对比 continue_text 和 text，找到 text 对应位置符号加入 seq_text
        b. 若非 a，且 token 不含 ##，直接加入 seq_text
        c. 若token ##，一直往后搜索直到不含 ##，并将搜索到的 token 加入 eng_text，然后按以下逻辑还原并加入 seq_text：
            1) 先聚合带 ## token 组成英文单词
            2) 再用空格间隔英文单词组成英文文本
            3) 对照原文还原大小写
    '''
    sequence_texts, continue_text = [], []
    for s_i, sequence in enumerate(sequences):
        seq_text, eng_text = [], []
        i = 0
        while True:
            if i >= len(sequence):
                break
            t = tokenizer.convert_ids_to_tokens(sequence[i])
            if t == '[UNK]':
                unk_t = text[len(''.join(continue_text))]
                seq_text.append(unk_t)
                continue_text.append(unk_t)
                i += 1
            elif not has_cut(t):
                seq_text.append(t)
                continue_text.append(t)
                i += 1
            else:
                while True:
                    eng_text.append(sequence[i]) 
                    i += 1
                    if i < len(sequence):
                        t = tokenizer.convert_ids_to_tokens(sequence[i])
                        if not has_cut(tokenizer.convert_ids_to_tokens(sequence[i])): # 搜索直到非英文
                            break
                    else:
                        break
                decode_eng_text = tokenizer.decode(eng_text)
                if decode_eng_text.startswith('##'):
                    decode_eng_text = decode_eng_text.strip('##') # 有时实体识别错误把英文单词一部分识别为实体，另一部分识别为 O, 导致某个 sequence 开头为 ##
                elif len(sequence_texts) > 0 and has_english(sequence_texts[-1][-1]) and has_english(decode_eng_text[0]) and has_english(continue_text[-1]):
                    decode_eng_text = ' ' + decode_eng_text 
                continue_text.append(decode_eng_text)
                seq_text.append(decode_eng_text)
                eng_text = []   
        sequence_texts.append(''.join(seq_text))
    return sequence_texts


def get_doccano_sample_v1(text_sequence, pred_sequence, tokenizer, text, return_raw=False):
    '''
    Get doccano sample of a single text sequence and prediction sequence

    Argument
    --------
    text_sequence: list
    pred_sequence: list

    修复英文的问题
    1. 按标签分出 sequence
    2. 按顺序将 sequence 转成 text
    '''
    assert len(text_sequence) == len(pred_sequence)
    doccano_text, doccano_label, part_text = [], [], [] # part_text 暂存同 label 的 sequence
    i = 0
    while i < len(text_sequence):
        t, p = text_sequence[i], pred_sequence[i]
        if i == 0 and text[i] == ' ': # doccano 会丢弃首位空格，导致 label 错位
            i += 1
            continue
        if p in ['O']:
            label_type = 'O'
            part_text.append(t)
            if i+1 < len(text_sequence) and pred_sequence[i+1].startswith('B_'):
                doccano_label.append(label_type)
        if p.startswith('B_'):
            label_type = p[2:]
            if (i+1 < len(text_sequence) and (pred_sequence[i+1].startswith('O') or pred_sequence[i+1].startswith('B_'))) or \
                (i+1 == len(text_sequence)): # 单 token 实体
                doccano_label.append(label_type)
                if len(part_text) > 0:
                    doccano_text.append(part_text) 
                doccano_text.append([t]) 
                part_text = []
            elif len(part_text) > 0:
                doccano_text.append(part_text)
                part_text = []
                part_text.append(t)
            else:
                part_text.append(t)
        if p.startswith('I_'):
            if i+1 < len(text_sequence) and ((pred_sequence[i+1] in ['O']) or (pred_sequence[i+1].startswith('B_'))):
                part_text.append(t)
                doccano_text.append(part_text)
                doccano_label.append(label_type)
                part_text = []
            else:
                part_text.append(t)
        i += 1
    doccano_text.append(part_text)
    doccano_label.append(label_type)
    doccano_text = transform_sequence_to_text(doccano_text, text, tokenizer)
    try:
        assert len(doccano_text) == len(doccano_label)
    except Exception as e:
        print('err: len(doccano_text) != len(doccano_label)',e)
        return
    label_start, i = 0, 0
    doccano_label_lst = []
    while i < len(doccano_text):
        if doccano_label[i] == 'O':
            label_start += len(doccano_text[i])
        else:
            doccano_label_lst.append([label_start, label_start+len(doccano_text[i]), doccano_label[i]])
            label_start += len(doccano_text[i])
        i += 1
    if return_raw:
        return doccano_text, doccano_label, doccano_label_lst
    return {'text':''.join(doccano_text), 'labels': doccano_label_lst}


