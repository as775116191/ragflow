#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import logging
from email import policy
from email.parser import BytesParser
from rag.app.naive import chunk as naive_chunk
import re
from rag.nlp import rag_tokenizer, naive_merge, tokenize_chunks
from deepdoc.parser import HtmlParser, TxtParser
from timeit import default_timer as timer
import io
import numpy as np


def chunk(
    filename,
    binary=None,
    from_page=0,
    to_page=100000,
    lang="Chinese",
    callback=None,
    **kwargs,
):
    """
    处理eml邮件，包括正文和附件内容
    Only eml is supported
    """
    eng = lang.lower() == "english"  # is_english(cks)
    parser_config = kwargs.get(
        "parser_config",
        {"chunk_token_num": 128, "delimiter": "\n!?。；！？", "layout_recognize": "DeepDOC"},
    )
    doc = {
        "docnm_kwd": filename,
        "title_tks": rag_tokenizer.tokenize(re.sub(r"\.[a-zA-Z]+$", "", filename)),
    }
    doc["title_sm_tks"] = rag_tokenizer.fine_grained_tokenize(doc["title_tks"])
    main_res = []
    attachment_res = []

    if binary:
        msg = BytesParser(policy=policy.default).parse(io.BytesIO(binary))
    else:
        msg = BytesParser(policy=policy.default).parse(open(filename, "rb"))

    text_txt, html_txt = [], []
    # 获取邮件头信息
    for header, value in msg.items():
        text_txt.append(f"{header}: {value}")

    # 保存内嵌图片的CID映射
    cid_images = {}
    
    # 处理内嵌图片和正文内容
    def _process_part(part):
        content_type = part.get_content_type()
        content_id = part.get("Content-ID")
        content_disposition = part.get("Content-Disposition")
        
        # 处理内嵌图片
        if content_id and ('image' in content_type.lower() or 
                          (content_disposition and 'inline' in content_disposition.lower())):
            # 提取CID，去除<>括号
            cid = content_id.strip('<>')
            payload = part.get_payload(decode=True)
            cid_images[f"cid:{cid}"] = payload
            return
            
        # 处理文本内容
        if content_type == "text/plain":
            text_txt.append(part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore'))
        elif content_type == "text/html":
            html_txt.append(part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore'))
        # 处理多部分内容
        elif "multipart" in content_type:
            if part.is_multipart():
                for subpart in part.iter_parts():
                    _process_part(subpart)
    
    # 处理邮件内容
    _process_part(msg)
    
    # 处理HTML中的内嵌图片
    tenant_id = kwargs.get("tenant_id")
    if tenant_id and html_txt and cid_images:
        try:
            from bs4 import BeautifulSoup
            from api.db import LLMType
            from api.db.services.llm_service import LLMBundle
            from deepdoc.vision import OCR
            from PIL import Image
            
            html_content = "\n".join(html_txt)
            soup = BeautifulSoup(html_content, 'html.parser')
            ocr = OCR()
            
            # 尝试加载CV模型
            try:
                cv_mdl = LLMBundle(tenant_id, LLMType.IMAGE2TEXT, lang=lang)
            except Exception as e:
                cv_mdl = None
                if callback:
                    callback(0.5, f"Warning: Cannot load CV model: {str(e)}")
            
            # 处理所有图片标签
            for img_tag in soup.find_all('img'):
                src = img_tag.get('src', '')
                if src in cid_images:
                    try:
                        # 提取图片内容
                        img_binary = cid_images[src]
                        img = Image.open(io.BytesIO(img_binary)).convert('RGB')
                        
                        # OCR处理
                        img_text = ""
                        bxs = ocr(np.array(img))
                        ocr_text = "\n".join([t[0] for _, t in bxs if t[0]])
                        if ocr_text:
                            img_text += f"[图片OCR文本: {ocr_text}]"
                        
                        # 使用CV模型描述图片
                        if cv_mdl:
                            img_buffer = io.BytesIO()
                            img.save(img_buffer, format='JPEG')
                            img_buffer.seek(0)
                            description = cv_mdl.describe(img_buffer.read())
                            if description:
                                img_text += f"[图片描述: {description}]"
                        
                        # 替换图片标签为描述文本
                        if img_text:
                            img_tag.replace_with(BeautifulSoup(img_text, 'html.parser'))
                    except Exception as e:
                        if callback:
                            callback(0.5, f"Warning: Error processing inline image: {str(e)}")
            
            # 更新处理后的HTML
            html_txt = [str(soup)]
        except ImportError as e:
            logging.warning(f"无法处理内嵌图片: {str(e)}，请安装缺失的依赖库")
        except Exception as e:
            logging.exception(f"处理内嵌图片时出错: {str(e)}")

    sections = TxtParser.parser_txt("\n".join(text_txt)) + [
        (line, "") for line in HtmlParser.parser_txt("\n".join(html_txt)) if line
    ]

    st = timer()
    chunks = naive_merge(
        sections,
        int(parser_config.get("chunk_token_num", 128)),
        parser_config.get("delimiter", "\n!?。；！？"),
    )

    main_res.extend(tokenize_chunks(chunks, doc, eng, None))
    logging.debug("naive_merge({}): {}".format(filename, timer() - st))
    
    # 处理常规附件
    for part in msg.iter_attachments():
        content_disposition = part.get("Content-Disposition")
        if content_disposition:
            dispositions = content_disposition.strip().split(";")
            if dispositions[0].lower() == "attachment":
                filename = part.get_filename()
                payload = part.get_payload(decode=True)
                try:
                    attachment_res.extend(
                        naive_chunk(filename, payload, callback=callback, **kwargs)
                    )
                except Exception:
                    pass

    return main_res + attachment_res


if __name__ == "__main__":
    import sys

    def dummy(prog=None, msg=""):
        pass

    chunk(sys.argv[1], callback=dummy)
