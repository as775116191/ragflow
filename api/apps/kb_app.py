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
#  limitations under the License.
#
import json
import os
import threading
import asyncio
import logging

from flask import request
from flask_login import login_required, current_user

from api.db.services import duplicate_name
from api.db.services.document_service import DocumentService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.file_service import FileService
from api.db.services.user_service import TenantService, UserTenantService
from api.utils.api_utils import server_error_response, get_data_error_result, validate_request, not_allowed_parameters
from api.utils import get_uuid
from api.db import StatusEnum, FileSource
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.db_models import File
from api.utils.api_utils import get_json_result
from api import settings
from rag.nlp import search
from api.constants import DATASET_NAME_LIMIT
from rag.settings import PAGERANK_FLD
from rag.utils.storage_factory import STORAGE_IMPL
from api.db import TenantPermission
from api.db.services.onedrive_sync_service import OneDriveSyncService
from api.db.services.outlook_sync_service import OutlookSyncService


# 导入同步状态管理
from api.db.services.sync_state import SYNCING_KNOWLEDGE_BASES

@manager.route('/create', methods=['post'])  # noqa: F821
@login_required
@validate_request("name")
def create():
    req = request.json
    dataset_name = req["name"]
    if not isinstance(dataset_name, str):
        return get_data_error_result(message="Dataset name must be string.")
    if dataset_name.strip() == "":
        return get_data_error_result(message="Dataset name can't be empty.")
    if len(dataset_name.encode("utf-8")) > DATASET_NAME_LIMIT:
        return get_data_error_result(
            message=f"Dataset name length is {len(dataset_name)} which is larger than {DATASET_NAME_LIMIT}")

    dataset_name = dataset_name.strip()
    dataset_name = duplicate_name(
        KnowledgebaseService.query,
        name=dataset_name,
        tenant_id=current_user.id,
        status=StatusEnum.VALID.value)
    try:
        req["id"] = get_uuid()
        req["name"] = dataset_name
        req["tenant_id"] = current_user.id
        req["created_by"] = current_user.id
        e, t = TenantService.get_by_id(current_user.id)
        if not e:
            return get_data_error_result(message="Tenant not found.")
        req["embd_id"] = t.embd_id
        
        # 处理权限为角色时的role_ids参数
        permission = req.get("permission")
        if permission == TenantPermission.ROLE.value:
            role_ids = req.get("role_ids", [])
            if not role_ids:
                return get_data_error_result(
                    message="Role IDs are required when permission is set to 'role'.")
        
        if not KnowledgebaseService.save(**req):
            return get_data_error_result()
        return get_json_result(data={"kb_id": req["id"]})
    except Exception as e:
        return server_error_response(e)


@manager.route('/update', methods=['post'])  # noqa: F821
@login_required
@validate_request("kb_id", "name", "description", "parser_id")
@not_allowed_parameters("id", "tenant_id", "created_by", "create_time", "update_time", "create_date", "update_date", "created_by")
def update():
    req = request.json
    if not isinstance(req["name"], str):
        return get_data_error_result(message="Dataset name must be string.")
    if req["name"].strip() == "":
        return get_data_error_result(message="Dataset name can't be empty.")
    if len(req["name"].encode("utf-8")) > DATASET_NAME_LIMIT:
        return get_data_error_result(
            message=f"Dataset name length is {len(req['name'])} which is large than {DATASET_NAME_LIMIT}")
    req["name"] = req["name"].strip()

    if not KnowledgebaseService.accessible4deletion(req["kb_id"], current_user.id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    try:
        if not KnowledgebaseService.query(
                created_by=current_user.id, id=req["kb_id"]):
            return get_json_result(
                data=False, message='Only owner of knowledgebase authorized for this operation.',
                code=settings.RetCode.OPERATING_ERROR)

        e, kb = KnowledgebaseService.get_by_id(req["kb_id"])
        if not e:
            return get_data_error_result(
                message="Can't find this knowledgebase!")

        if req.get("parser_id", "") == "tag" and os.environ.get('DOC_ENGINE', "elasticsearch") == "infinity":
            return get_json_result(
                data=False,
                message='The chunking method Tag has not been supported by Infinity yet.',
                code=settings.RetCode.OPERATING_ERROR
            )

        if req["name"].lower() != kb.name.lower() \
                and len(
            KnowledgebaseService.query(name=req["name"], tenant_id=current_user.id, status=StatusEnum.VALID.value)) >= 1:
            return get_data_error_result(
                message="Duplicated knowledgebase name.")

        # 处理权限为角色时的role_ids参数
        permission = req.get("permission")
        if permission == TenantPermission.ROLE.value:
            role_ids = req.get("role_ids", [])
            if not role_ids:
                return get_data_error_result(
                    message="Role IDs are required when permission is set to 'role'.")
        
        # 处理Outlook邮箱同步配置
        parser_config = req.get("parser_config", {})
        if parser_config.get("outlook_sync_enabled", False):
            # 验证邮箱和文件夹是否填写
            outlook_email = parser_config.get("outlook_email")
            outlook_folder = parser_config.get("outlook_folder")
            if not outlook_email or not outlook_folder:
                return get_data_error_result(
                    message="Outlook email and folder are required when sync is enabled.")
            
            # 不设置上次同步时间，首次同步将获取所有邮件
        else:
            # 保留上次同步时间记录，以便将来再次启用时使用
            kb_parser_config = kb.parser_config or {}
            if kb_parser_config.get("outlook_last_sync") and "outlook_last_sync" not in parser_config:
                parser_config["outlook_last_sync"] = kb_parser_config.get("outlook_last_sync")

        del req["kb_id"]
        if not KnowledgebaseService.update_by_id(kb.id, req):
            return get_data_error_result()

        if kb.pagerank != req.get("pagerank", 0):
            if os.environ.get("DOC_ENGINE", "elasticsearch") != "elasticsearch":
                return get_data_error_result(message="'pagerank' can only be set when doc_engine is elasticsearch")
            
            if req.get("pagerank", 0) > 0:
                settings.docStoreConn.update({"kb_id": kb.id}, {PAGERANK_FLD: req["pagerank"]},
                                         search.index_name(kb.tenant_id), kb.id)
            else:
                # Elasticsearch requires PAGERANK_FLD be non-zero!
                settings.docStoreConn.update({"exists": PAGERANK_FLD}, {"remove": PAGERANK_FLD},
                                         search.index_name(kb.tenant_id), kb.id)

        e, kb = KnowledgebaseService.get_by_id(kb.id)
        if not e:
            return get_data_error_result(
                message="Database error (Knowledgebase rename)!")
        kb = kb.to_dict()
        kb.update(req)

        return get_json_result(data=kb)
    except Exception as e:
        return server_error_response(e)


@manager.route('/detail', methods=['GET'])  # noqa: F821
@login_required
def detail():
    kb_id = request.args["kb_id"]
    try:
        tenants = UserTenantService.query(user_id=current_user.id)
        for tenant in tenants:
            if KnowledgebaseService.query(
                    tenant_id=tenant.tenant_id, id=kb_id):
                break
        else:
            return get_json_result(
                data=False, message='Only owner of knowledgebase authorized for this operation.',
                code=settings.RetCode.OPERATING_ERROR)
        kb = KnowledgebaseService.get_detail(kb_id)
        if not kb:
            return get_data_error_result(
                message="Can't find this knowledgebase!")
        kb["size"] = DocumentService.get_total_size_by_kb_id(kb_id=kb["id"],keywords="", run_status=[], types=[])
        return get_json_result(data=kb)
    except Exception as e:
        return server_error_response(e)


@manager.route('/list', methods=['POST'])  # noqa: F821
@login_required
def list_kbs():
    keywords = request.args.get("keywords", "")
    page_number = int(request.args.get("page", 0))
    items_per_page = int(request.args.get("page_size", 0))
    parser_id = request.args.get("parser_id")
    orderby = request.args.get("orderby", "create_time")
    if request.args.get("desc", "true").lower() == "false":
        desc = False
    else:
        desc = True

    req = request.get_json()
    owner_ids = req.get("owner_ids", [])
    try:
        if not owner_ids:
            tenants = TenantService.get_joined_tenants_by_user_id(current_user.id)
            tenants = [m["tenant_id"] for m in tenants]
            kbs, total = KnowledgebaseService.get_by_tenant_ids(
                tenants, current_user.id, page_number,
                items_per_page, orderby, desc, keywords, parser_id)
        else:
            tenants = owner_ids
            kbs, total = KnowledgebaseService.get_by_tenant_ids(
                tenants, current_user.id, 0,
                0, orderby, desc, keywords, parser_id)
            kbs = [kb for kb in kbs if kb["tenant_id"] in tenants]
            total = len(kbs)
            if page_number and items_per_page:
                kbs = kbs[(page_number-1)*items_per_page:page_number*items_per_page]
        return get_json_result(data={"kbs": kbs, "total": total})
    except Exception as e:
        return server_error_response(e)

@manager.route('/rm', methods=['post'])  # noqa: F821
@login_required
@validate_request("kb_id")
def rm():
    req = request.json
    if not KnowledgebaseService.accessible4deletion(req["kb_id"], current_user.id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    try:
        kbs = KnowledgebaseService.query(
            created_by=current_user.id, id=req["kb_id"])
        if not kbs:
            return get_json_result(
                data=False, message='Only owner of knowledgebase authorized for this operation.',
                code=settings.RetCode.OPERATING_ERROR)

        for doc in DocumentService.query(kb_id=req["kb_id"]):
            if not DocumentService.remove_document(doc, kbs[0].tenant_id):
                return get_data_error_result(
                    message="Database error (Document removal)!")
            f2d = File2DocumentService.get_by_document_id(doc.id)
            if f2d:
                FileService.filter_delete([File.source_type == FileSource.KNOWLEDGEBASE, File.id == f2d[0].file_id])
            File2DocumentService.delete_by_document_id(doc.id)
        FileService.filter_delete(
            [File.source_type == FileSource.KNOWLEDGEBASE, File.type == "folder", File.name == kbs[0].name])
        if not KnowledgebaseService.delete_by_id(req["kb_id"]):
            return get_data_error_result(
                message="Database error (Knowledgebase removal)!")
        for kb in kbs:
            settings.docStoreConn.delete({"kb_id": kb.id}, search.index_name(kb.tenant_id), kb.id)
            settings.docStoreConn.deleteIdx(search.index_name(kb.tenant_id), kb.id)
            if hasattr(STORAGE_IMPL, 'remove_bucket'):
                STORAGE_IMPL.remove_bucket(kb.id)
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/<kb_id>/tags', methods=['GET'])  # noqa: F821
@login_required
def list_tags(kb_id):
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )

    tags = settings.retrievaler.all_tags(current_user.id, [kb_id])
    return get_json_result(data=tags)


@manager.route('/tags', methods=['GET'])  # noqa: F821
@login_required
def list_tags_from_kbs():
    kb_ids = request.args.get("kb_ids", "").split(",")
    for kb_id in kb_ids:
        if not KnowledgebaseService.accessible(kb_id, current_user.id):
            return get_json_result(
                data=False,
                message='No authorization.',
                code=settings.RetCode.AUTHENTICATION_ERROR
            )

    tags = settings.retrievaler.all_tags(current_user.id, kb_ids)
    return get_json_result(data=tags)


@manager.route('/<kb_id>/rm_tags', methods=['POST'])  # noqa: F821
@login_required
def rm_tags(kb_id):
    req = request.json
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    e, kb = KnowledgebaseService.get_by_id(kb_id)

    for t in req["tags"]:
        settings.docStoreConn.update({"tag_kwd": t, "kb_id": [kb_id]},
                                     {"remove": {"tag_kwd": t}},
                                     search.index_name(kb.tenant_id),
                                     kb_id)
    return get_json_result(data=True)


@manager.route('/<kb_id>/rename_tag', methods=['POST'])  # noqa: F821
@login_required
def rename_tags(kb_id):
    req = request.json
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    e, kb = KnowledgebaseService.get_by_id(kb_id)

    settings.docStoreConn.update({"tag_kwd": req["from_tag"], "kb_id": [kb_id]},
                                     {"remove": {"tag_kwd": req["from_tag"].strip()}, "add": {"tag_kwd": req["to_tag"]}},
                                     search.index_name(kb.tenant_id),
                                     kb_id)
    return get_json_result(data=True)


@manager.route('/<kb_id>/knowledge_graph', methods=['GET'])  # noqa: F821
@login_required
def knowledge_graph(kb_id):
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    _, kb = KnowledgebaseService.get_by_id(kb_id)
    req = {
        "kb_id": [kb_id],
        "knowledge_graph_kwd": ["graph"]
    }

    obj = {"graph": {}, "mind_map": {}}
    if not settings.docStoreConn.indexExist(search.index_name(kb.tenant_id), kb_id):
        return get_json_result(data=obj)
    sres = settings.retrievaler.search(req, search.index_name(kb.tenant_id), [kb_id])
    if not len(sres.ids):
        return get_json_result(data=obj)

    for id in sres.ids[:1]:
        ty = sres.field[id]["knowledge_graph_kwd"]
        try:
            content_json = json.loads(sres.field[id]["content_with_weight"])
        except Exception:
            continue

        obj[ty] = content_json

    if "nodes" in obj["graph"]:
        obj["graph"]["nodes"] = sorted(obj["graph"]["nodes"], key=lambda x: x.get("pagerank", 0), reverse=True)[:256]
        if "edges" in obj["graph"]:
            node_id_set = { o["id"] for o in obj["graph"]["nodes"] }
            filtered_edges = [o for o in obj["graph"]["edges"] if o["source"] != o["target"] and o["source"] in node_id_set and o["target"] in node_id_set]
            obj["graph"]["edges"] = sorted(filtered_edges, key=lambda x: x.get("weight", 0), reverse=True)[:128]
    return get_json_result(data=obj)

@manager.route('/<kb_id>/knowledge_graph', methods=['DELETE'])  # noqa: F821
@login_required
def delete_knowledge_graph(kb_id):
    if not KnowledgebaseService.accessible(kb_id, current_user.id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    _, kb = KnowledgebaseService.get_by_id(kb_id)
    settings.docStoreConn.delete({"knowledge_graph_kwd": ["graph", "subgraph", "entity", "relation"]}, search.index_name(kb.tenant_id), kb_id)

    return get_json_result(data=True)

@manager.route("/sync_status", methods=["GET"])  # noqa: F821
@login_required
def get_sync_status():
    """获取知识库同步状态"""
    kb_id = request.args.get('kb_id')
    
    if not kb_id:
        return get_json_result(data=SYNCING_KNOWLEDGE_BASES, message="返回所有正在同步的知识库")
    
    # 检查指定知识库是否正在同步
    if kb_id in SYNCING_KNOWLEDGE_BASES:
        return get_json_result(data={
            "is_syncing": True,
            "sync_type": SYNCING_KNOWLEDGE_BASES[kb_id]["type"]
        })
    else:
        return get_json_result(data={"is_syncing": False})

@manager.route("/trigger_sync", methods=["POST"])  # noqa: F821
@login_required
@validate_request("kb_id", "sync_type")
def trigger_sync():
    """触发单个知识库的同步"""
    req = request.json
    kb_id = req["kb_id"]
    sync_type = req["sync_type"]  # onedrive 或 outlook
    
    # 获取可选的邮箱和文件夹参数（用于"立即同步"）
    email = req.get("email")
    folder_name = req.get("folder_name")  # for outlook
    folder_path = req.get("folder_path")  # for onedrive
    
    # 检查知识库是否存在
    e, kb = KnowledgebaseService.get_by_id(kb_id)
    if not e:
        return get_data_error_result(message="知识库不存在")
    
    # 在触发同步之前，先保存配置信息到知识库
    parser_config = getattr(kb, 'parser_config', {}) or {}
    config_updated = False
    
    if sync_type == "onedrive":
        # 保存OneDrive配置
        if email:
            parser_config["onedrive_email"] = email
            config_updated = True
        if folder_path:
            parser_config["onedrive_folder_path"] = folder_path
            config_updated = True
        # 启用OneDrive同步
        parser_config["onedrive_sync_enabled"] = True
        config_updated = True
    elif sync_type == "outlook":
        # 保存Outlook配置
        if email:
            parser_config["outlook_email"] = email
            config_updated = True
        if folder_name:
            parser_config["outlook_folder"] = folder_name
            config_updated = True
        # 启用Outlook同步
        parser_config["outlook_sync_enabled"] = True
        config_updated = True
    
    # 如果配置有更新，保存到数据库
    if config_updated:
        try:
            KnowledgebaseService.update_by_id(kb_id, {"parser_config": parser_config})
            logging.info(f"已保存知识库 {kb_id} 的{sync_type}同步配置")
        except Exception as e:
            logging.error(f"保存知识库 {kb_id} 的{sync_type}同步配置失败: {str(e)}")
            return get_json_result(data=False, message=f"保存配置失败: {str(e)}", code=settings.RetCode.SERVER_ERROR)
    
    # 检查知识库是否已在同步中
    if kb_id in SYNCING_KNOWLEDGE_BASES:
        return get_json_result(data=False, message=f"该知识库正在进行{SYNCING_KNOWLEDGE_BASES[kb_id]['type']}同步，请稍后再试", code=settings.RetCode.ARGUMENT_ERROR)
    
    # 创建后台任务执行同步
    try:
        if sync_type == "onedrive":
            # 创建线程执行OneDrive同步
            thread = threading.Thread(
                target=_run_onedrive_sync,
                args=(kb_id, email, folder_path),
                daemon=True
            )
            SYNCING_KNOWLEDGE_BASES[kb_id] = {"type": "onedrive", "task": thread}
            thread.start()
        elif sync_type == "outlook":
            # 创建线程执行Outlook同步
            thread = threading.Thread(
                target=_run_outlook_sync,
                args=(kb_id, email, folder_name),
                daemon=True
            )
            SYNCING_KNOWLEDGE_BASES[kb_id] = {"type": "outlook", "task": thread}
            thread.start()
        else:
            return get_json_result(data=False, message="不支持的同步类型", code=settings.RetCode.ARGUMENT_ERROR)
        
        return get_json_result(data=True, message=f"{sync_type}同步任务已启动")
    except Exception as e:
        if kb_id in SYNCING_KNOWLEDGE_BASES:
            del SYNCING_KNOWLEDGE_BASES[kb_id]
        return server_error_response(e)


@manager.route("/cancel_sync", methods=["POST"])  # noqa: F821
@login_required
@validate_request("kb_id")
def cancel_sync():
    """取消知识库同步"""
    req = request.json
    kb_id = req["kb_id"]
    
    if kb_id not in SYNCING_KNOWLEDGE_BASES:
        return get_json_result(data=False, message="该知识库未在同步中", code=settings.RetCode.ARGUMENT_ERROR)
    
    # 标记任务为取消
    SYNCING_KNOWLEDGE_BASES[kb_id]["cancelled"] = True
    
    # 等待任务结束
    import time
    max_wait = 30  # 最多等待30秒
    waited = 0
    while kb_id in SYNCING_KNOWLEDGE_BASES and waited < max_wait:
        time.sleep(1)
        waited += 1
    
    return get_json_result(data=True, message="同步任务已取消")


def _run_onedrive_sync(kb_id, email=None, folder_path=None):
    """在后台执行单个知识库的OneDrive同步"""
    try:
        logging.info(f"开始执行OneDrive同步任务，知识库ID: {kb_id}")
        # 创建事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 执行同步（强制同步，跳过同步开关检查）
        loop.run_until_complete(OneDriveSyncService.sync_single_kb(kb_id, force_sync=True, email=email, folder_path=folder_path))
        loop.close()
        logging.info(f"OneDrive同步任务完成，知识库ID: {kb_id}")
    except Exception as e:
        logging.exception(f"OneDrive同步任务执行失败，知识库ID: {kb_id}, 错误: {str(e)}")
    finally:
        # 无论成功失败，都从同步列表中移除
        if kb_id in SYNCING_KNOWLEDGE_BASES:
            del SYNCING_KNOWLEDGE_BASES[kb_id]
        logging.info(f"OneDrive同步任务结束，知识库ID: {kb_id}")

def _run_outlook_sync(kb_id, email=None, folder_name=None):
    """在后台执行单个知识库的Outlook同步"""
    try:
        logging.info(f"开始执行Outlook同步任务，知识库ID: {kb_id}")
        # 创建事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 执行同步（强制同步，跳过同步开关检查）
        loop.run_until_complete(OutlookSyncService.sync_single_kb(kb_id, force_sync=True, email=email, folder_name=folder_name))
        loop.close()
        logging.info(f"Outlook同步任务完成，知识库ID: {kb_id}")
    except Exception as e:
        logging.exception(f"Outlook同步任务执行失败，知识库ID: {kb_id}, 错误: {str(e)}")
    finally:
        # 无论成功失败，都从同步列表中移除
        if kb_id in SYNCING_KNOWLEDGE_BASES:
            del SYNCING_KNOWLEDGE_BASES[kb_id]
        logging.info(f"Outlook同步任务结束，知识库ID: {kb_id}")
