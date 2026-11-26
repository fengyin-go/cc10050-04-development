"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import parser_review, resource

# parser_review 是字面量前缀，放在动态 /{module} 资源路由之前注册。
ROUTERS = [parser_review, resource]
