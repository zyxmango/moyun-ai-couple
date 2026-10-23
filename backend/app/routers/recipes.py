"""情侣菜谱路由"""
import json
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Couple, Recipe, RecipeRating, RecipeComment
from ..schemas import (
    RecipeCreate, RecipeUpdate, RecipeOut,
    RecipeCommentCreate, RecipeCommentOut, ApiResponse,
)
from ..deps import get_current_user, get_active_couple
from ..config import settings

router = APIRouter(prefix="/api/recipes", tags=["情侣菜谱"])


def _recipe_out(r: Recipe, user_id: int, db: Session) -> dict:
    """组装菜谱输出（含评分、留言数、厨师昵称）"""
    # 平均评分
    ratings = db.query(RecipeRating).filter(RecipeRating.recipe_id == r.id).all()
    avg_score = round(sum(rt.score for rt in ratings) / len(ratings), 1) if ratings else 0.0
    my_score = next((rt.score for rt in ratings if rt.user_id == user_id), 0)

    # 厨师昵称
    chef = db.query(User).filter(User.id == r.chef_id).first() if r.chef_id else None
    author = db.query(User).filter(User.id == r.author_id).first()

    comment_count = db.query(RecipeComment).filter(RecipeComment.recipe_id == r.id).count()

    return {
        "id": r.id,
        "couple_id": r.couple_id,
        "author_id": r.author_id,
        "author_nickname": author.nickname if author else "",
        "chef_id": r.chef_id,
        "chef_nickname": chef.nickname if chef else "",
        "title": r.title,
        "cover": r.cover or "",
        "category": r.category,
        "difficulty": r.difficulty,
        "cook_time": r.cook_time,
        "ingredients": json.loads(r.ingredients) if r.ingredients else [],
        "steps": json.loads(r.steps) if r.steps else [],
        "cook_count": r.cook_count,
        "want_eat": r.want_eat,
        "avg_score": avg_score,
        "my_score": my_score,
        "comment_count": comment_count,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


# ---------- CRUD ----------
@router.get("")
def list_recipes(
    category: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    chef: Optional[str] = Query(None),  # "me" / "partner" / "want_eat"
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """获取菜谱列表（支持筛选）"""
    q = db.query(Recipe).filter(Recipe.couple_id == couple.id)
    if category:
        q = q.filter(Recipe.category == category)
    if difficulty:
        q = q.filter(Recipe.difficulty == difficulty)
    if chef == "me":
        q = q.filter(Recipe.chef_id == user.id)
    elif chef == "partner":
        partner_id = couple.user2_id if couple.user1_id == user.id else couple.user1_id
        q = q.filter(Recipe.chef_id == partner_id)
    elif chef == "want_eat":
        q = q.filter(Recipe.want_eat == True)

    recipes = q.order_by(Recipe.created_at.desc()).all()
    return [_recipe_out(r, user.id, db) for r in recipes]


@router.get("/random")
def random_recipe(
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """随机推荐一道菜谱"""
    recipes = db.query(Recipe).filter(Recipe.couple_id == couple.id).all()
    if not recipes:
        raise HTTPException(status_code=404, detail="还没有菜谱，先添加一道吧")
    r = random.choice(recipes)
    return _recipe_out(r, user.id, db)


@router.get("/{recipe_id}")
def get_recipe(
    recipe_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """获取菜谱详情"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    return _recipe_out(r, user.id, db)


@router.post("")
def create_recipe(
    req: RecipeCreate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """创建菜谱"""
    r = Recipe(
        couple_id=couple.id,
        author_id=user.id,
        chef_id=req.chef_id or user.id,
        title=req.title,
        cover=req.cover,
        category=req.category,
        difficulty=req.difficulty,
        cook_time=req.cook_time,
        ingredients=json.dumps([i.dict() for i in req.ingredients], ensure_ascii=False),
        steps=json.dumps(req.steps, ensure_ascii=False),
        want_eat=req.want_eat,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _recipe_out(r, user.id, db)


@router.put("/{recipe_id}")
def update_recipe(
    recipe_id: int,
    req: RecipeUpdate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """更新菜谱"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    if req.title is not None:
        r.title = req.title
    if req.cover is not None:
        r.cover = req.cover
    if req.category is not None:
        r.category = req.category
    if req.difficulty is not None:
        r.difficulty = req.difficulty
    if req.cook_time is not None:
        r.cook_time = req.cook_time
    if req.chef_id is not None:
        r.chef_id = req.chef_id
    if req.ingredients is not None:
        r.ingredients = json.dumps([i.dict() for i in req.ingredients], ensure_ascii=False)
    if req.steps is not None:
        r.steps = json.dumps(req.steps, ensure_ascii=False)
    if req.want_eat is not None:
        r.want_eat = req.want_eat

    db.commit()
    db.refresh(r)
    return _recipe_out(r, user.id, db)


@router.delete("/{recipe_id}", response_model=ApiResponse)
def delete_recipe(
    recipe_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """删除菜谱"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    db.delete(r)
    db.commit()
    return ApiResponse(message="已删除")


# ---------- 评分 ----------
@router.post("/{recipe_id}/rate")
def rate_recipe(
    recipe_id: int,
    score: int = Query(..., ge=1, le=5),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """给菜谱评分（1-5，每人一次，重复则覆盖）"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    existing = db.query(RecipeRating).filter(
        RecipeRating.recipe_id == recipe_id,
        RecipeRating.user_id == user.id,
    ).first()
    if existing:
        existing.score = score
    else:
        rating = RecipeRating(recipe_id=recipe_id, user_id=user.id, score=score)
        db.add(rating)
    db.commit()
    return _recipe_out(r, user.id, db)


# ---------- 留言 ----------
@router.get("/{recipe_id}/comments", response_model=List[RecipeCommentOut])
def list_comments(
    recipe_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """获取菜谱留言"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    comments = db.query(RecipeComment).filter(RecipeComment.recipe_id == recipe_id).order_by(RecipeComment.id).all()
    result = []
    for c in comments:
        u = db.query(User).filter(User.id == c.user_id).first()
        result.append({
            "id": c.id, "user_id": c.user_id,
            "user_nickname": u.nickname if u else "",
            "content": c.content, "created_at": c.created_at.isoformat(),
        })
    return result


@router.post("/{recipe_id}/comments", response_model=RecipeCommentOut)
def add_comment(
    recipe_id: int,
    req: RecipeCommentCreate,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """添加留言"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="留言不能为空")
    c = RecipeComment(recipe_id=recipe_id, user_id=user.id, content=req.content.strip())
    db.add(c)
    db.commit()
    db.refresh(c)
    return {
        "id": c.id, "user_id": c.user_id, "user_nickname": user.nickname,
        "content": c.content, "created_at": c.created_at.isoformat(),
    }


@router.delete("/{recipe_id}/comments/{comment_id}", response_model=ApiResponse)
def delete_comment(
    recipe_id: int,
    comment_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """删除留言"""
    c = db.query(RecipeComment).filter(
        RecipeComment.id == comment_id,
        RecipeComment.recipe_id == recipe_id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="留言不存在")
    if c.user_id != user.id:
        raise HTTPException(status_code=403, detail="只能删除自己的留言")
    db.delete(c)
    db.commit()
    return ApiResponse(message="已删除")


# ---------- 烹饪记录 ----------
@router.post("/{recipe_id}/cook", response_model=ApiResponse)
def record_cook(
    recipe_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """记录一次烹饪（cook_count +1，并取消想吃标记）"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    r.cook_count = (r.cook_count or 0) + 1
    r.want_eat = False
    db.commit()
    return ApiResponse(message=f"已记录第 {r.cook_count} 次烹饪")


# ---------- 想吃清单 ----------
@router.put("/{recipe_id}/want-eat", response_model=ApiResponse)
def toggle_want_eat(
    recipe_id: int,
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
    db: Session = Depends(get_db),
):
    """切换想吃标记"""
    r = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.couple_id == couple.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    r.want_eat = not r.want_eat
    db.commit()
    return ApiResponse(message="已添加到想吃清单" if r.want_eat else "已移出想吃清单")


# ---------- 封面上传 ----------
@router.post("/upload-cover")
async def upload_cover(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    couple: Couple = Depends(get_active_couple),
):
    """上传菜谱封面图"""
    import uuid
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    if ext.lower() not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 格式")
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = settings.PHOTOS_DIR / filename
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 50MB")
    filepath.write_bytes(content)
    return {"url": f"/uploads/photos/{filename}"}
