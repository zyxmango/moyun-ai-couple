"""RAG 旅游记录智能体路由"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, Document, DocumentChunk, AIConversation, AIMessage, AICallLog
from ..schemas import RAGChatRequest, RAGChatResponse, DocumentOut, RAGTextUploadRequest
from ..deps import get_current_user, get_active_couple
from ..services.rag_service import rag_service
from ..services.ai_service import ai_service

router = APIRouter(prefix="/api/rag", tags=["RAG旅游智能体"])


def _extract_text(filename: str, raw: bytes) -> str:
    """从上传文件提取纯文本"""
    text = ""
    try:
        if filename.lower().endswith(".txt"):
            text = raw.decode("utf-8", errors="ignore")
        elif filename.lower().endswith(".md"):
            text = raw.decode("utf-8", errors="ignore")
        elif filename.lower().endswith((".json",)):
            text = raw.decode("utf-8", errors="ignore")
        else:
            # 尝试 utf-8 解码（兼容直接粘贴的文本类文件）
            text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    return text


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    content = _extract_text(file.filename, raw)
    if not content.strip():
        raise HTTPException(status_code=400, detail="无法从文件中提取文本内容")

    doc = Document(couple_id=couple.id, filename=file.filename, content=content)
    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunk_count = rag_service.add_document(doc.id, content, couple.id)
    return {"id": doc.id, "filename": doc.filename, "chunk_count": chunk_count, "message": "文档已上传并完成向量化"}


@router.post("/upload-text")
def upload_text_document(
    req: RAGTextUploadRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """直接通过文本内容上传文档"""
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="文档内容不能为空")

    title = req.title.strip() or "未命名文档"
    doc = Document(couple_id=couple.id, filename=title, content=content)
    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunk_count = rag_service.add_document(doc.id, content, couple.id)
    return {"id": doc.id, "filename": doc.filename, "chunk_count": chunk_count, "message": "文档已保存并完成向量化"}


@router.get("/documents")
def list_documents(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    docs = db.query(Document).filter(Document.couple_id == couple.id).order_by(Document.created_at.desc()).all()
    return [{"id": d.id, "filename": d.filename, "chunk_count": d.chunk_count,
             "created_at": d.created_at.isoformat()} for d in docs]


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.couple_id == couple.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    rag_service.remove_document(doc.id)
    db.delete(doc)
    db.commit()
    return {"message": "文档已删除"}


@router.post("/chat", response_model=RAGChatResponse)
def rag_chat(
    req: RAGChatRequest,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    # 检索相关切片
    sources = rag_service.search(req.question, couple.id, top_k=3)
    context = "\n\n".join([f"[来源: {s['source']}] {s['content']}" for s in sources]) if sources else "（知识库中暂无相关内容）"

    # 获取或创建对话
    if req.conversation_id:
        conv = db.query(AIConversation).filter(
            AIConversation.id == req.conversation_id,
            AIConversation.user_id == user.id,
            AIConversation.conv_type == "rag",
        ).first()
    else:
        conv = AIConversation(user_id=user.id, conv_type="rag", title=req.question[:20])
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # 保存用户消息
    db.add(AIMessage(conversation_id=conv.id, role="user", content=req.question))
    db.commit()

    # 构建历史
    msgs = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).order_by(AIMessage.id).all()
    history = [{"role": m.role, "content": m.content} for m in msgs[-20:][:-1]]

    # 调用 AI
    answer = ai_service.rag_answer(req.question, context, history)

    # 保存 AI 回复（带来源）
    sources_json = json.dumps(sources, ensure_ascii=False)
    ai_msg = AIMessage(conversation_id=conv.id, role="assistant", content=answer, sources=sources_json)
    db.add(ai_msg)
    log = AICallLog(user_id=user.id, feature="rag", input_text=req.question,
                    output_text=answer, status="success")
    db.add(log)
    db.commit()
    db.refresh(ai_msg)

    return RAGChatResponse(answer=answer, sources=sources, conversation_id=conv.id)


@router.get("/history")
def rag_history(
    conversation_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AIConversation).filter(
        AIConversation.user_id == user.id, AIConversation.conv_type == "rag"
    )
    if conversation_id:
        query = query.filter(AIConversation.id == conversation_id)
    convs = query.order_by(AIConversation.created_at.desc()).all()
    result = []
    for conv in convs:
        msgs = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).order_by(AIMessage.id).all()
        result.append({
            "id": conv.id, "title": conv.title, "created_at": conv.created_at.isoformat(),
            "messages": [{
                "id": m.id, "role": m.role, "content": m.content,
                "sources": json.loads(m.sources) if m.sources else [],
                "created_at": m.created_at.isoformat(),
            } for m in msgs],
        })
    return result
