from vyper import ast as vy_ast

from vyro.cairo.import_directives import add_builtin_to_module
from vyro.cairo.types import CairoUint256Definition, get_cairo_type
from vyro.transpiler.visitor import BaseVisitor


class BinOpConverterVisitor(BaseVisitor):
    def visit_BinOp(self, node, ast, context):
        typ = node._metadata.get("type")
        cairo_typ = get_cairo_type(typ)

        op = node.op

        if isinstance(op, vy_ast.Mod):
            vyro_op = (
                "vyro_mod256"
                if isinstance(cairo_typ, CairoUint256Definition)
                else "vyro_mod"
            )
        else:
            return

        # Wrap left and right in a function call
        wrapped_op = vy_ast.Call(
            node_id=context.reserve_id(),
            func=vy_ast.Name(node_id=context.reserve_id(), id=vyro_op, ast_type="Name"),
            args=vy_ast.arguments(
                node_id=context.reserve_id(),
                args=[node.left, node.right],
                ast_type="arguments",
            ),
            keywords=[],
        )

        # Replace `BinOp` node with wrapped call
        ast.replace_in_tree(node, wrapped_op)

        # Add import
        add_builtin_to_module(ast, vyro_op)
