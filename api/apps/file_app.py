#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
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
#  limitations under the License
#
import os
import pathlib
import re

import flask
from flask import request
from flask_login import login_required, current_user

from api.db.services.document_service import DocumentService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.file_service import FileService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.utils.api_utils import server_error_response, get_data_error_result, validate_request
from api.utils import get_uuid
from api.db import FileType, FileSource
from api.db.services import duplicate_name
from api import settings
from api.utils.api_utils import get_json_result
from api.utils.file_utils import filename_type
from api.utils.web_utils import CONTENT_TYPE_MAP
from rag.utils.storage_factory import STORAGE_IMPL


@manager.route('/upload', methods=['POST'])  # noqa: F821
@login_required
# @validate_request("parent_id")
def upload():
    pf_id = request.form.get("parent_id")

    if not pf_id:
        root_folder = FileService.get_root_folder(current_user.id)
        pf_id = root_folder["id"]

    if 'file' not in request.files:
        return get_json_result(
            data=False, message='No file part!', code=settings.RetCode.ARGUMENT_ERROR)
    file_objs = request.files.getlist('file')

    for file_obj in file_objs:
        if file_obj.filename == '':
            return get_json_result(
                data=False, message='No file selected!', code=settings.RetCode.ARGUMENT_ERROR)
    file_res = []
    try:
        e, pf_folder = FileService.get_by_id(pf_id)
        if not e:
            return get_data_error_result( message="Can't find this folder!")
        for file_obj in file_objs:
            MAX_FILE_NUM_PER_USER = int(os.environ.get('MAX_FILE_NUM_PER_USER', 0))
            if MAX_FILE_NUM_PER_USER > 0 and DocumentService.get_doc_count(current_user.id) >= MAX_FILE_NUM_PER_USER:
                return get_data_error_result( message="Exceed the maximum file number of a free user!")

            # split file name path
            if not file_obj.filename:
                file_obj_names = [pf_folder.name, file_obj.filename]
            else:
                full_path = '/' + file_obj.filename
                file_obj_names = full_path.split('/')
            file_len = len(file_obj_names)

            # get folder
            file_id_list = FileService.get_id_list_by_id(pf_id, file_obj_names, 1, [pf_id])
            len_id_list = len(file_id_list)

            # create folder
            if file_len != len_id_list:
                e, file = FileService.get_by_id(file_id_list[len_id_list - 1])
                if not e:
                    return get_data_error_result(message="Folder not found!")
                last_folder = FileService.create_folder(file, file_id_list[len_id_list - 1], file_obj_names,
                                                        len_id_list)
            else:
                e, file = FileService.get_by_id(file_id_list[len_id_list - 2])
                if not e:
                    return get_data_error_result(message="Folder not found!")
                last_folder = FileService.create_folder(file, file_id_list[len_id_list - 2], file_obj_names,
                                                        len_id_list)

            # file type
            filetype = filename_type(file_obj_names[file_len - 1])
            location = file_obj_names[file_len - 1]
            while STORAGE_IMPL.obj_exist(last_folder.id, location):
                location += "_"
            blob = file_obj.read()
            filename = duplicate_name(
                FileService.query,
                name=file_obj_names[file_len - 1],
                parent_id=last_folder.id)
            STORAGE_IMPL.put(last_folder.id, location, blob)
            file = {
                "id": get_uuid(),
                "parent_id": last_folder.id,
                "tenant_id": current_user.id,
                "created_by": current_user.id,
                "type": filetype,
                "name": filename,
                "location": location,
                "size": len(blob),
            }
            file = FileService.insert(file)
            STORAGE_IMPL.put(last_folder.id, location, blob)
            file_json = file.to_json()
            
            # 检查父文件夹是否有关联的知识库，如果有则自动关联上传的文件
            parent_kbs_info = FileService.get_kb_id_by_file_id(last_folder.id)
            if parent_kbs_info:
                kb_info = []
                for kb_info_item in parent_kbs_info:
                    kb_id = kb_info_item["kb_id"]
                    e, kb = KnowledgebaseService.get_by_id(kb_id)
                    if not e:
                        continue
                        
                    # 创建文档并关联
                    doc = DocumentService.insert({
                        "id": get_uuid(),
                        "kb_id": kb.id,
                        "parser_id": FileService.get_parser(filetype, filename, kb.parser_id),
                        "parser_config": kb.parser_config,
                        "created_by": current_user.id,
                        "type": filetype,
                        "name": filename,
                        "location": location,
                        "size": len(blob)
                    })
                    File2DocumentService.insert({
                        "id": get_uuid(),
                        "file_id": file.id,
                        "document_id": doc.id,
                    })
                    kb_info.append({
                        "kb_id": kb.id,
                        "kb_name": kb.name,
                        "doc_id": doc.id
                    })
                file_json["kb_info"] = kb_info
                
            file_res.append(file_json)
            
        return get_json_result(data=file_res)
    except Exception as e:
        return server_error_response(e)


@manager.route('/create', methods=['POST'])  # noqa: F821
@login_required
@validate_request("name")
def create():
    req = request.json
    pf_id = request.json.get("parent_id")
    input_file_type = request.json.get("type")
    if not pf_id:
        root_folder = FileService.get_root_folder(current_user.id)
        pf_id = root_folder["id"]

    try:
        if not FileService.is_parent_folder_exist(pf_id):
            return get_json_result(
                data=False, message="Parent Folder Doesn't Exist!", code=settings.RetCode.OPERATING_ERROR)
        if FileService.query(name=req["name"], parent_id=pf_id):
            return get_data_error_result(
                message="Duplicated folder name in the same folder.")

        if input_file_type == FileType.FOLDER.value:
            file_type = FileType.FOLDER.value
        else:
            file_type = FileType.VIRTUAL.value

        file = FileService.insert({
            "id": get_uuid(),
            "parent_id": pf_id,
            "tenant_id": current_user.id,
            "created_by": current_user.id,
            "name": req["name"],
            "location": "",
            "size": 0,
            "type": file_type
        })
        
        # 检查父文件夹是否有关联的知识库，如果有则自动为新文件夹建立关联
        if file_type == FileType.FOLDER.value:
            parent_kbs_info = FileService.get_kb_id_by_file_id(pf_id)
            if parent_kbs_info:
                kb_info = []
                for kb_info_item in parent_kbs_info:
                    kb_id = kb_info_item["kb_id"]
                    e, kb = KnowledgebaseService.get_by_id(kb_id)
                    if not e:
                        continue
                        
                    # 为新文件夹创建关联记录，无需文档ID
                    File2DocumentService.insert({
                        "id": get_uuid(),
                        "file_id": file.id,
                        "kb_id": kb.id,
                        "document_id": None  # 文件夹不需要文档ID
                    })
                    kb_info.append({
                        "kb_id": kb.id,
                        "kb_name": kb.name,
                        "doc_id": None
                    })
                
                # 将知识库信息添加到返回结果中
                file_json = file.to_json()
                file_json["kb_info"] = kb_info
                return get_json_result(data=file_json)

        return get_json_result(data=file.to_json())
    except Exception as e:
        return server_error_response(e)


@manager.route('/list', methods=['GET'])  # noqa: F821
@login_required
def list_files():
    pf_id = request.args.get("parent_id")

    keywords = request.args.get("keywords", "")

    page_number = int(request.args.get("page", 1))
    items_per_page = int(request.args.get("page_size", 15))
    orderby = request.args.get("orderby", "create_time")
    desc = request.args.get("desc", True)
    if not pf_id:
        root_folder = FileService.get_root_folder(current_user.id)
        pf_id = root_folder["id"]
        FileService.init_knowledgebase_docs(pf_id, current_user.id)
    try:
        e, file = FileService.get_by_id(pf_id)
        if not e:
            return get_data_error_result(message="Folder not found!")

        files, total = FileService.get_by_pf_id(
            current_user.id, pf_id, page_number, items_per_page, orderby, desc, keywords)

        parent_folder = FileService.get_parent_folder(pf_id)
        if not parent_folder:
            return get_json_result(message="File not found!")

        return get_json_result(data={"total": total, "files": files, "parent_folder": parent_folder.to_json()})
    except Exception as e:
        return server_error_response(e)


@manager.route('/root_folder', methods=['GET'])  # noqa: F821
@login_required
def get_root_folder():
    try:
        root_folder = FileService.get_root_folder(current_user.id)
        return get_json_result(data={"root_folder": root_folder})
    except Exception as e:
        return server_error_response(e)


@manager.route('/parent_folder', methods=['GET'])  # noqa: F821
@login_required
def get_parent_folder():
    file_id = request.args.get("file_id")
    try:
        e, file = FileService.get_by_id(file_id)
        if not e:
            return get_data_error_result(message="Folder not found!")

        parent_folder = FileService.get_parent_folder(file_id)
        return get_json_result(data={"parent_folder": parent_folder.to_json()})
    except Exception as e:
        return server_error_response(e)


@manager.route('/all_parent_folder', methods=['GET'])  # noqa: F821
@login_required
def get_all_parent_folders():
    file_id = request.args.get("file_id")
    try:
        e, file = FileService.get_by_id(file_id)
        if not e:
            return get_data_error_result(message="Folder not found!")

        parent_folders = FileService.get_all_parent_folders(file_id)
        parent_folders_res = []
        for parent_folder in parent_folders:
            parent_folders_res.append(parent_folder.to_json())
        return get_json_result(data={"parent_folders": parent_folders_res})
    except Exception as e:
        return server_error_response(e)


@manager.route('/rm', methods=['POST'])  # noqa: F821
@login_required
@validate_request("file_ids")
def rm():
    req = request.json
    file_ids = req["file_ids"]
    try:
        for file_id in file_ids:
            e, file = FileService.get_by_id(file_id)
            if not e:
                return get_data_error_result(message="File or Folder not found!")
            if not file.tenant_id:
                return get_data_error_result(message="Tenant not found!")
            if file.source_type == FileSource.KNOWLEDGEBASE:
                continue

            if file.type == FileType.FOLDER.value:
                # 递归获取所有子文件和子文件夹
                file_id_list = []
                # 首先把当前文件夹ID添加到列表中
                file_id_list.append(file_id)
                
                # 获取所有内部文件ID（包括子文件夹下的文件）
                query = FileService.model.select().where(FileService.model.parent_id == file_id)
                for inner_file in query:
                    if inner_file.type == FileType.FOLDER.value:
                        # 递归获取子文件夹下的所有文件ID
                        inner_ids = FileService.get_all_innermost_file_ids(inner_file.id, [])
                        file_id_list.extend(inner_ids)
                    else:
                        # 直接添加文件ID
                        file_id_list.append(inner_file.id)
                
                # 处理所有文件
                for inner_file_id in file_id_list:
                    e, inner_file = FileService.get_by_id(inner_file_id)
                    if not e:
                        return get_data_error_result(message="File not found!")
                    
                    # 删除文件的文档关联
                    inner_informs = File2DocumentService.get_by_file_id(inner_file_id)
                    for inner_inform in inner_informs:
                        if not inner_inform:
                            continue
                            
                        inner_doc_id = inner_inform.document_id
                        # 文件夹关联知识库时document_id为null，跳过文档删除
                        if inner_doc_id is None:
                            continue
                            
                        e, inner_doc = DocumentService.get_by_id(inner_doc_id)
                        if not e:
                            return get_data_error_result(message="Document not found!")
                            
                        inner_tenant_id = DocumentService.get_tenant_id(inner_doc_id)
                        if not inner_tenant_id:
                            return get_data_error_result(message="Tenant not found!")
                            
                        if not DocumentService.remove_document(inner_doc, inner_tenant_id):
                            return get_data_error_result(
                                message="Database error (Document removal)!")
                                
                    File2DocumentService.delete_by_file_id(inner_file_id)
                    
                    # 删除文件本身（只针对非文件夹）
                    if inner_file.type != FileType.FOLDER.value and inner_file_id != file_id:
                        STORAGE_IMPL.rm(inner_file.parent_id, inner_file.location)
                
                # 删除文件夹结构
                FileService.delete_folder_by_pf_id(current_user.id, file_id)
            else:
                STORAGE_IMPL.rm(file.parent_id, file.location)
                if not FileService.delete(file):
                    return get_data_error_result(
                        message="Database error (File removal)!")

            # delete file2document
            informs = File2DocumentService.get_by_file_id(file_id)
            for inform in informs:
                doc_id = inform.document_id
                # 文件夹关联知识库时document_id为null，跳过文档删除
                if doc_id is None:
                    continue
                    
                e, doc = DocumentService.get_by_id(doc_id)
                if not e:
                    return get_data_error_result(message="Document not found!")
                tenant_id = DocumentService.get_tenant_id(doc_id)
                if not tenant_id:
                    return get_data_error_result(message="Tenant not found!")
                if not DocumentService.remove_document(doc, tenant_id):
                    return get_data_error_result(
                        message="Database error (Document removal)!")
            File2DocumentService.delete_by_file_id(file_id)

        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/rename', methods=['POST'])  # noqa: F821
@login_required
@validate_request("file_id", "name")
def rename():
    req = request.json
    try:
        e, file = FileService.get_by_id(req["file_id"])
        if not e:
            return get_data_error_result(message="File not found!")
        if file.type != FileType.FOLDER.value \
            and pathlib.Path(req["name"].lower()).suffix != pathlib.Path(
                file.name.lower()).suffix:
            return get_json_result(
                data=False,
                message="The extension of file can't be changed",
                code=settings.RetCode.ARGUMENT_ERROR)
        for file in FileService.query(name=req["name"], pf_id=file.parent_id):
            if file.name == req["name"]:
                return get_data_error_result(
                    message="Duplicated file name in the same folder.")

        if not FileService.update_by_id(
                req["file_id"], {"name": req["name"]}):
            return get_data_error_result(
                message="Database error (File rename)!")

        informs = File2DocumentService.get_by_file_id(req["file_id"])
        if informs:
            if not DocumentService.update_by_id(
                    informs[0].document_id, {"name": req["name"]}):
                return get_data_error_result(
                    message="Database error (Document rename)!")

        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/get/<file_id>', methods=['GET'])  # noqa: F821
@login_required
def get(file_id):
    try:
        e, file = FileService.get_by_id(file_id)
        if not e:
            return get_data_error_result(message="Document not found!")

        blob = STORAGE_IMPL.get(file.parent_id, file.location)
        if not blob:
            b, n = File2DocumentService.get_storage_address(file_id=file_id)
            blob = STORAGE_IMPL.get(b, n)

        response = flask.make_response(blob)
        ext = re.search(r"\.([^.]+)$", file.name.lower())
        ext = ext.group(1) if ext else None
        if ext:
            if file.type == FileType.VISUAL.value:
                content_type = CONTENT_TYPE_MAP.get(ext, f"image/{ext}")
            else:
                content_type = CONTENT_TYPE_MAP.get(ext, f"application/{ext}")
            response.headers.set("Content-Type", content_type)
        return response
    except Exception as e:
        return server_error_response(e)


@manager.route('/mv', methods=['POST'])  # noqa: F821
@login_required
@validate_request("src_file_ids", "dest_file_id")
def move():
    req = request.json
    try:
        file_ids = req["src_file_ids"]
        parent_id = req["dest_file_id"]
        files = FileService.get_by_ids(file_ids)
        files_dict = {}
        for file in files:
            files_dict[file.id] = file

        for file_id in file_ids:
            file = files_dict[file_id]
            if not file:
                return get_data_error_result(message="File or Folder not found!")
            if not file.tenant_id:
                return get_data_error_result(message="Tenant not found!")
        fe, _ = FileService.get_by_id(parent_id)
        if not fe:
            return get_data_error_result(message="Parent Folder not found!")
        FileService.move_file(file_ids, parent_id)
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
