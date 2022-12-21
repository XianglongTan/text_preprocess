import camelot
import base64
import re
import pickpdf
import os
import pandas as pd
import uuid


def pike_clean(path:str):
    # 处理加密的 pdf
    file_name = path.split("/")[-1]
    new_file_name = 'unencrypted_'+file_name
    clean_file_path = '.'
    if not os.path.exists(clean_file_path):
        os.mkdir(clean_file_path)
    new_file_path = os.path.join(clean_file_path, new_file_name)
    pdf = pikepdf.open(path)
    pdf.save(new_file_path)
    return new_file_path


def mutool_clean(path:str):
    new_file_name = 'clean_' + path.split('/')[-1]
    new_path = '/' + os.path.join(*path.split('/')[:-1], new_file_name)
    # with fitz.open(path) as doc
    #     doc.save(new_path, clean=True)
    os.system(f"mutool clean {path} {new_path}")
    return new_path


def base64decode(x:str):
    return base64.b64decode(x)


def camelot_process(path:str, page:int):
    page = str(page)
    tables = []
    line_scale = 25

    try:
        tables = camelot.read_pdf(path, pages=page, split_text=True, line_scale=line_scale)
        if len(tables) > 0:
            return tables
        else:
            raise Exception
        
    except: # 处理加密的 pdf
        new_path = pike_clean(path)
        try:
            tables = camelot.read_pdf(new_path, pages=page, split_text=True, line_scale=line_scale)
            if len(tables) > 0:
                return tables
            else:
                raise IndexError
        except IndexError:
            try:
                tables = camelot.read_pdf(new_path, pages=page, split_text=False, line_scale=line_scale)
                if len(tables) > 0:
                    return tables
                else:
                    raise IndexError
            except IndexError:
                try:
                    tables = camelot.read_pdf(path, pages=page, flavor='stream', row_tol=25, flag_size=True) # 获取表格型文本
                    no_line_tables = []
                    for i in range(len(tables)):
                        no_line_table = clean_no_line_table(tables[i].df) 
                        if no_line_table is not None:
                            no_line_tables.append(no_line_table)
                    return no_line_tables
                except IndexError:
                    return tables    
    return tables


def request_frame_all(path:str, pdf_struct:dict, pdf_bytes:str, start_page:int, end_page:int):
    if start_page > end_page:
        raise ValueError("start_page must be smaller than end_page")
    path = mutool_clean(path)

    # 开始处理
    # 这里 p 是实际页码减1 
    # camelot 用的则是 p+1
    # page_updated 通常是 p+1 
    all_dataframe = []
    page_index_rec = []
    num_pages = len(pdf_struct['text'])
    page_updated = -1
    
    for p in range(start_page, end_page+1):
        tables = camelot_process(path, p+1)
        # print(p, len(tables))
        if len(tables) <= 0:
            continue
        df_p = pd.DataFrame([])

        # 记录跨页情况， 如循环的p小于更新页，证明有跨页，跳过
        if page_updated > p+1:
            continue
        
        # 看跨页的最后一页，以防有多个表格
        elif page_updated == p+1:
            if len(tables) <= 1:
                continue
            for i in range(1, len(tables)):                
                if i < len(tables)-1:
                    if isinstance(tables[i], pd.DataFrame):
                        all_dataframe.append(tables[i])
                    else:
                        all_dataframe.append(tables[i].df)
                else: # 最后一个表格做跨页判定
                    df_last, last_page = cross_page(pdf_struct, path, p+1, len(tables)-1, df_p, use_plumber=False)
                    all_dataframe.append(df_last)               
                    page_updated = last_page

                page_index_rec.append(f"{p+1}_{i}")                            
        
        # 如无跨页情况，正常判断
        elif page_updated < p+1 and len(tables) >= 1:
            for i in range(len(tables)):
                if i < len(tables)-1:
                    if isinstance(tables[i], pd.DataFrame):
                        all_dataframe.append(tables[i])
                    else:
                        all_dataframe.append(tables[i].df)
                else:
                    df_last, last_page = cross_page(pdf_struct, path, p+1, len(tables)-1, df_p, use_plumber=False)
                    all_dataframe.append(df_last)
                    page_updated = last_page # last_page 也是 p+1
                page_index_rec.append(f"{p+1}_{i}")
    
    all_dataframe_json = []
    if all_dataframe:
        for df_ in all_dataframe:
            df_ = df_.dropna(how='all')
            df_ = df_.dropna(how='all', axis=1)
            all_dataframe_json.append(df_.to_json(orient="index",force_ascii=False))

    # all_dataframe_json: list, page_index_rec: list
    return all_dataframe_json, page_index_rec      


def cross_page(pdf_object:dict, pdf_path:str, page:int, pos, df_previous, use_plumber=False, auto_mode=False):
    # page: 实际页码
    if isinstance(pdf_object, dict):
        text = pdf_object['text'][page-1]
    else:    
        text = pdf_object.pages[page-1].extract_text()
    try:
        if isinstance(pdf_object, dict):
            text2 = pdf_object['text'][page]
        else:
            text2 = pdf_object.pages[page].extract_text()
    except Exception as e:
        text2 = ""

    df_null = pd.DataFrame([])

    ## frist table
    if df_previous.empty:
        if use_plumber:
            if isinstance(pdf_object, dict):
                tables_backup = pdf_object['tables'][page-1]
            else:
                tables_backup = pdf_object.pages[page-1].extract_tables()
            if len(tables_backup) == 0 or not tables_backup:
                return df_null, page
            df1 = pd.DataFrame(tables_backup[-1])
        else:
            # 存在错行会使用camelot
            tables = camelot_process(pdf_path, page)
            if len(tables) <= 0:
                return df_null, page
            if pos <= len(tables)-1:
                if isinstance(tables[pos], pd.DataFrame):
                    df1 = tables[pos]
                else:
                    df1 = tables[pos].df
            else:
                raise Exception("pos must be smaller than tables length")
    else:
        df1 = df_previous

    # process before_page_text
    text = text.split("\n")
    text = [x for x in text if len(re.sub("\s","", x)) != 0]
    clean_text_pat = r"\s|\n|[\.,-/%]+|（[^）]*）"
    split_text_new = re.sub(r"\n|[（）\.,-]", "", "".join(text[-1:]))
    split_text_new_ = re.split(r"[\s]", split_text_new)
    split_text = re.sub(clean_text_pat, "", "".join(text[-1:])) # 包含页码，最后一行，未含页脚
    if len(split_text) < 5:
        split_text = re.sub(clean_text_pat, "", "".join(text[-2:]))
        if len(split_text) < 5:
            split_text = re.sub(clean_text_pat, "", "".join(text[-3:]))
    df1_tail_text_lst = [x for x in df1.tail(1).values[0] if x]
    before_table_text = re.sub(clean_text_pat, "", "".join(df1_tail_text_lst)) # 表格最后一行
    before_table_text_10 = before_table_text
    if len(before_table_text)>10:
        before_table_text_10 = before_table_text[-10:]
    score1 = find_lcsubstr(before_table_text_10.strip(), split_text.strip())
    score1_1 = find_lcsubstr(before_table_text.strip(), split_text.strip())
    socre1_max = round(max(score1, score1_1), 3)
    max_score = 0
    for token in split_text_new_:
        score1_ = find_lcsubstr(before_table_text.strip(), token.strip())
        max_score = max(max_score, score1_)
    if score1 < 0.02:
        return df1, page
   
    ## second table
    if page < len(pdf_object['tables']):
        tables2 = camelot_process(pdf_path, page+1)
        if len(tables2) <= 0:
            return df1, page

    text2 = text2.split("\n")
    text2 = [x for x in text2 if len(re.sub("\s","", x)) != 0]
    split_text2 = re.sub(r"\s|\n|[.,-]","","".join(text2[1:]))
    if len(split_text2) > 15:
        split_text2 = split_text2[:15]
    if isinstance(tables2[0], pd.DataFrame):
        df2 = tables2[0]
    else:
        df2 = tables2[0].df
    df2_head = df2.head(2).values
    after_table_text = re.sub(r"\s|\n|[.,-]","","".join(["".join([x for x in row if x]) for row in df2_head]))
    tmp_df1_head = re.sub(r"\s|\n|[.,-]","","".join(["".join([str(x) for x in row if x]) for row in df1.head(1).values]))
    score2 = round(find_lcsubstr(after_table_text.strip(), split_text2.strip()), 3)
    tmp_score = round(find_lcsubstr(after_table_text.strip(), tmp_df1_head.strip()), 3)
    if (socre1_max > 0.15 and score2 > 0.05) or (tmp_score > 0.5 and score2 > 0.05):
        if len(tables2) ==1:
            df_ff = merge_row_simple(df1, df2, pdf_object, page+1)
            if df_ff.empty:
                return df1, page
            return cross_page(pdf_object, pdf_path, page+1, 0, df_ff, use_plumber)

        elif len(tables2) >1:
            df_ff = merge_row_simple(df1, df2, pdf_object, page+1)
            if df_ff.empty:
                return df1, page
            return df_ff, page+1
    else:
        return df1, page


def find_lcsubstr(s1, s2): 
    # 生成0矩阵，为方便后续计算，比字符串长度多了一列
    m = [[0 for i in range(len(s2)+1)] for j in range(len(s1)+1)] 
    mmax = 0   # 最长匹配的长度
    p = 0  # 最长匹配对应在s1中的最后一位
    for i in range(len(s1)):
        for j in range(len(s2)):
            if s1[i] == s2[j]:
                m[i+1][j+1] = m[i][j] + 1
                if m[i+1][j+1] > mmax:
                    mmax = m[i+1][j+1]
                    p = i+1
    
    max_len = max(len(s1), len(s2))
    if mmax <=1:
        mmax = 0
    per = mmax/(max_len+0.000000001)

    if mmax == 2 and per < 0.15:
        per = 0

    return per


def merge_row_simple(df1, df2, pdf_object, page):

    null_df = pd.DataFrame([])
    
    df_all = []
    merge_condition = merge_identify(df1,df2)
    # print(merge_condition)
    # print(df1, df2)
    if merge_condition[1]:
        df2 = df2.iloc[1:,:]

    df1_tail = df1.tail(1).values[0]
    df2_head = df2.head(1).values[0]
    # print(df1_tail, df2_head)

    if len(df1_tail) != len(df2_head):
        # print('Merge by the second way')
        if isinstance(pdf_object, dict):
            tables_backup = pdf_object['tables'][page-1]
        else:
            tables_backup = pdf_object.pages[page-1].extract_tables()
        
        # print(tables_backup)
        try:
            df2 = pd.DataFrame(tables_backup[0]) # why -1 not 0
            df2_head = df2.head(1).values[0]
        
            if len(df1_tail) != len(df2_head):
                # print('Merge Failed')
                return null_df

            if merge_condition[1]:
                df2 = df2.iloc[1:,:] 
        except:
            return null_df

    if merge_condition[0]:

        n = len(df1_tail)
        df_row_merge = [str(df1_tail[i]) + str(df2_head[i]) for i in range(n)]
        # print(df_row_merge)
        # print(df1)
        df2 = df2.iloc[1:,:]
        # print(df1)
        # print(df2)

        df1.tail(1).values[0] = df_row_merge
    
    df_all.append(df1)
    df_all.append(df2)

    df_final = pd.concat(df_all).reset_index(drop=True)

    return df_final


def get_tables(pdf_bytes:str, pdf_struct:dict, start_page:int, end_page:int):
    file_name = str(uuid.uuid4()) + '.pdf'
    file_path = os.path.join(os.getcwd(), file_name)
    try:
        data_bytes = base64decode(pdf_bytes)
        with open(file_path, 'wb') as f:
            f.write(data_bytes)
        all_df, df_index_rec = request_frame_all(file_path, pdf_struct, data_bytes, start_page, end_page)
        return all_df, df_index_rec
    except Exception as e:
        raise Exception(e)
    finally:
        if os.path.exists(os.path.join(os.getcwd(), file_name)):
            os.remove(os.path.join(os.getcwd(), file_name))
        if os.path.exists(os.path.join(os.getcwd(), 'clean_'+file_name)):
            os.remove(os.path.join(os.getcwd(), 'clean_'+file_name))
        if os.path.exists(os.path.join(os.getcwd(), 'unencrypted_clean_'+file_name)):
            os.remove(os.path.join(os.getcwd(), 'unencrypted_clean_'+file_name))


def merge_identify(df1, df2):
    # two condition: merge or not
    merge = 0
    col_exist = 0
    df1_head = df1.head(1).values[0]
    df2_head = df2.head(1).values[0]
    df1_head_text = "".join([str(x) for x in list(df1_head)]).strip()
    df1_head_text = re.sub(r"\n", "", df1_head_text)
    df2_head_text = "".join([str(x) for x in list(df2_head)]).strip()
    df2_head_text = re.sub(r"\n", "", df2_head_text)

    # tow dataframe have same col_names
    if find_lcsubstr(df1_head_text, df2_head_text) > 0.5:
        col_exist = 1
    
    useless_cell = 0
    if col_exist:
        df2_head = df2.head(2).values[1]
    
    for cell in df2_head:
        if cell == "" or cell is None:
            useless_cell += 1
    
    if useless_cell/len(df2_head)>0.5:
        merge = 1

    return merge, col_exist


def clean_no_line_table(table):
    '''
    处理2列式表格式文本

    Arguments
    -------
    table: pd.DataFrame
    '''
    if table.shape[1] != 2:
        return None
    table.replace('', None, inplace=True)
    null_rate = table.isnull().sum() / len(table)
    if null_rate.mean() > 0.3:
        return None
    
    fill_na_col, group_col = table.columns[0], table.columns[1]
    table[fill_na_col] = table[fill_na_col].fillna(method='ffill')
    table[group_col] = table[group_col].fillna('')
    return table.groupby(fill_na_col, as_index=False)[group_col].apply(group_value)
    
    
def group_value(value):
    return ''.join(x for x in value if x != '')
