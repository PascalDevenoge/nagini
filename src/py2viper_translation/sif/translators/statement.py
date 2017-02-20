import ast

from py2viper_translation.lib.typedefs import Expr, StmtsAndExpr
from py2viper_translation.lib.util import (
    flatten,
    get_body_start_index,
    InvalidProgramException,
    UnsupportedException,
)
from py2viper_translation.sif.lib.context import SIFContext
from py2viper_translation.translators.abstract import Stmt
from py2viper_translation.translators.statement import StatementTranslator
from typing import List


class SIFStatementTranslator(StatementTranslator):
    """
    Secure Information Flow version of the StatementTranslator.
    """

    def translate_stmt(self, node: ast.AST, ctx: SIFContext) -> List[Stmt]:
        # New statement means we always updated the __new_tl var before, thus
        # we use that and reset the current TL var expression.
        ctx.current_tl_var_expr = None
        return super().translate_stmt(node, ctx)

    def translate_stmt_If(self, node: ast.If, ctx: SIFContext) -> List[Stmt]:
        """
        SIF translation of if-statements.

        ```
        #!rst

        Python:
            if cond:
                then_body
            else:
                else_body

        Silver:

        .. code-block:: silver
            tl = tl || cond != cond_p
            if(cond) {
                sif(then_body)
            } else {
                sif(else_body)
            }
        ```
        """
        pos = self.to_position(node, ctx)
        info = self.no_info(ctx)

        tl_stmts, if_cond = self._create_condition_and_timelevel_statements(
            node.test, ctx)

        # Translate the bodies.
        then_body = flatten([self.translate_stmt(stmt, ctx)
                             for stmt in node.body])
        then_block = self.translate_block(then_body, pos, info)
        else_body = flatten([self.translate_stmt(stmt, ctx)
                             for stmt in node.orelse])
        else_block = self.translate_block(else_body, pos, info)
        if_stmt = self.viper.If(if_cond, then_block, else_block, pos, info)

        return tl_stmts + [if_stmt]

    def translate_stmt_Assign(self, node: ast.Assign,
                              ctx: SIFContext) -> List[Stmt]:
        if len(node.targets) != 1:
            raise UnsupportedException(node)
        if isinstance(node.targets[0], ast.Subscript):
            raise UnsupportedException(node)

        # First translate assignment for normal variables.
        stmts = super().translate_stmt_Assign(node, ctx)
        # Translate assignment for prime variables.
        with ctx.prime_ctx():
            stmts += super().translate_stmt_Assign(node, ctx)

        # Update timelevel after function call or subscript.
        update_tl = isinstance(node.value, ast.Subscript)
        if isinstance(node.value, ast.Call):
            target = self.get_target(node.value, ctx)
            update_tl = target.pure

        if update_tl:
            tl_stmts, tl_expr = self.translate_expr(
                node.value, ctx, target_type=self.viper.Bool)
            assert not tl_stmts
            tl_assign = self.viper.LocalVarAssign(
                ctx.actual_function.new_tl_var.ref(), tl_expr,
                self.to_position(node, ctx), self.no_info(ctx))
            stmts.append(tl_assign)

        return stmts

    def translate_stmt_While(self, node: ast.While,
                             ctx: SIFContext) -> List[Stmt]:
        post_label = ctx.actual_function.get_fresh_name('post_loop')
        end_label = ctx.actual_function.get_fresh_name('loop_end')
        self.enter_loop_translation(node, post_label, end_label, ctx)
        tl_stmts, while_cond = self._create_condition_and_timelevel_statements(
            node.test, ctx)
        # Translate loop invariants.
        invariants = []
        for expr, aliases in ctx.actual_function.loop_invariants[node]:
            with ctx.additional_aliases(aliases):
                ctx.current_tl_var_expr = None
                invariant = self.translate_contract(expr, ctx)
                invariants.append(invariant)

        body_index = get_body_start_index(node.body)
        var_types = self._get_havoced_var_type_info(node.body[body_index:], ctx)
        invariants = var_types + invariants
        body = flatten([self.translate_stmt(stmt, ctx) for stmt in
                        node.body[body_index:]])
        # Add timelevel statement at the end of the loop.
        body.extend(tl_stmts)
        loop_stmts = self.create_while_node(ctx, while_cond, invariants, [],
                                            body, node)
        self.leave_loop_translation(ctx)
        res = tl_stmts + loop_stmts
        return res

    def _get_havoced_var_type_info(self, nodes: List[ast.AST],
                                   ctx: SIFContext) -> List[Expr]:
        """
        Creates a list of assertions containing type information for all local
        variables written to within the given partial ASTs which already
        existed before.
        To be used to remember type information about arguments/local variables
        which are assigned to in loops and therefore havoced.
        """
        result = []
        vars = self._get_havoced_vars(nodes, ctx)
        for var in vars:
            result.append(self.type_check(var.ref(), var.type,
                                          self.no_position(ctx), ctx))
            result.append(self.type_check(var.var_prime.ref(), var.type,
                                          self.no_position(ctx), ctx))
        return result

    def _create_condition_and_timelevel_statements(self, condition: ast.AST,
            ctx: SIFContext) -> StmtsAndExpr:
        """
        Creates the timelevel statement before ifs and whiles.

        Returns:
            List of statements for the timelevel update and the translated
            condition.
        """
        pos = self.to_position(condition, ctx)
        info = self.no_info(ctx)
        # Translate condition twice, once normally and once in the prime ctx.
        cond_stmts, cond = self.translate_expr(condition, ctx,
                                               target_type=self.viper.Bool)
        with ctx.prime_ctx():
            cond_stmts_p, cond_p = self.translate_expr(
                condition, ctx, target_type=self.viper.Bool)
        # tl := tl || cond != cond_p
        cond_cmp = self.viper.NeCmp(cond, cond_p, pos, info)
        or_expr = self.viper.Or(ctx.current_tl_var_expr, cond_cmp, pos, info)
        tl_assign = self.viper.LocalVarAssign(
            ctx.actual_function.new_tl_var.ref(), or_expr, pos, info)

        if cond_stmts or cond_stmts_p:
            raise InvalidProgramException(condition, 'purity.violated')

        return cond_stmts + cond_stmts_p + [tl_assign], cond

    def _translate_return(self, node: ast.Return,
                          ctx: SIFContext) -> List[Stmt]:
        pos = self.to_position(node, ctx)
        info = self.no_info(ctx)
        rhs_stmt, rhs = self.translate_expr(node.value, ctx)
        with ctx.prime_ctx():
            rhs_stmt_p, rhs_p = self.translate_expr(node.value, ctx)
        assign = self.viper.LocalVarAssign(
            ctx.current_function.result.ref(node, ctx), rhs, pos, info)
        assign_p = self.viper.LocalVarAssign(
            ctx.current_function.result.var_prime.ref(), rhs_p, pos, info)
        res = rhs_stmt + [assign] + rhs_stmt_p + [assign_p]
        if isinstance(node.value, ast.Call):
            _, tl_expr = self.translate_expr(node.value, ctx)
            assign_tl = self.viper.LocalVarAssign(
                ctx.current_function.new_tl_var.ref(),
                self.to_bool(tl_expr, ctx), pos, info)
            res.append(assign_tl)

        return res
