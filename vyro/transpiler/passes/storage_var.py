from vyper import ast as vy_ast
from vyper.semantics.types.function import (
    ContractFunction,
    FunctionVisibility,
    StateMutability,
)

from vyro.cairo.nodes import CairoStorageRead, CairoStorageWrite
from vyro.cairo.types import vyper_type_to_cairo_type
from vyro.transpiler.context import ASTContext
from vyro.transpiler.utils import convert_node_type_definition, generate_name_node, insert_statement_before, set_parent
from vyro.transpiler.visitor import BaseVisitor


class StorageVarVisitor(BaseVisitor):
    def visit_VariableDecl(
        self, node: vy_ast.VariableDecl, ast: vy_ast.Module, context: ASTContext
    ):
        # Store original variable name
        var_name = node.target.id

        # Update type
        vy_typ = node._metadata["type"]
        cairo_typ = vyper_type_to_cairo_type(vy_typ)
        node._metadata["type"] = cairo_typ

        if node.is_public is True:
            # Create temporary variable for assignment of storage read value
            temp_name_node = generate_name_node(context.reserve_id())
            temp_name_node._metadata["type"] = cairo_typ

            value_node = vy_ast.Name(
                node_id=context.reserve_id(),
                id=f"{var_name}_STORAGE",
                ast_type="Name",
            )

            # Create storage read node
            storage_read_node = CairoStorageRead(
                node_id=context.reserve_id(),
                parent=ast,
                targets=[temp_name_node],
                value=value_node,
            )
            storage_read_node._children.add(value_node)
            storage_read_node._children.add(temp_name_node)

            return_node = vy_ast.Name.from_node(
                temp_name_node,
                id=temp_name_node.id,
                node_id=context.reserve_id(),
            )
            return_node._metadata["type"] = cairo_typ

            fn_node_args = vy_ast.arguments(
                node_id=context.reserve_id(), args=[], defaults=[]
            )

            fn_node = vy_ast.FunctionDef(
                node_id=context.reserve_id(),
                name=var_name,
                body=[storage_read_node],
                args=fn_node_args,
                returns=return_node,
                decorator_list=None,
                doc_string=None,
            )

            fn_node._children.add(storage_read_node)
            fn_node._children.add(fn_node_args)
            fn_node._children.add(return_node)

            fn_node_typ = ContractFunction(
                name=var_name,
                arguments={},
                min_arg_count=0,
                max_arg_count=0,
                return_type=cairo_typ,
                function_visibility=FunctionVisibility.EXTERNAL,
                state_mutability=StateMutability.VIEW,
            )

            fn_node._metadata["type"] = fn_node_typ

            ast.add_to_body(fn_node)

    def visit_Assign(
        self, node: vy_ast.Assign, ast: vy_ast.Module, context: ASTContext
    ):
        # Check for storage variable on LHS of assignment
        lhs = node.target
        contract_var = lhs.get_children(vy_ast.Name, {"id": "self"})

        cairo_typ = convert_node_type_definition(node.target)

        if contract_var:
            # Create new variable and assign RHS
            rhs_name_node = generate_name_node(context.reserve_id())
            rhs_assignment_node = vy_ast.Assign(
                node_id=context.reserve_id(),
                targets=[rhs_name_node],
                value=node.value,
            )
            rhs_assignment_node._children.add(rhs_name_node)
            rhs_assignment_node._children.add(node.value)
            set_parent(node.value, rhs_assignment_node)

            # Add storage write node to body of function

            fn_node = node.get_ancestor(vy_ast.FunctionDef)

            # Create storage write node
            contract_var_attribute = contract_var.pop().get_ancestor()

            value_node = vy_ast.Name.from_node(
                rhs_name_node,
                id=rhs_name_node.id,
                node_id=context.reserve_id(),
            )

            storage_write_node = CairoStorageWrite(
                node_id=context.reserve_id(),
                parent=fn_node,
                targets=[
                    vy_ast.Name(
                        node_id=context.reserve_id(),
                        id=f"{contract_var_attribute.attr}_STORAGE",
                        ast_type="Name",
                    ),
                ],
                value=value_node,
            )
            storage_write_node._children.add(value_node)

            # Update type
            storage_write_node._metadata["type"] = cairo_typ
            storage_write_node.value._metadata["type"] = cairo_typ
            storage_write_node.target._metadata["type"] = cairo_typ

            # Replace assign node with RHS
            ast.replace_in_tree(node, storage_write_node)
            # Add RHS node before storage write node
            insert_statement_before(
                rhs_assignment_node, storage_write_node, fn_node
            )
