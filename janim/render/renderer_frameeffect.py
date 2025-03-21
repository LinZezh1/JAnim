from __future__ import annotations

from typing import TYPE_CHECKING

import moderngl as mgl
import numpy as np

from janim.anims.animation import Animation
from janim.render.base import (Renderer, blend_context, create_framebuffer,
                               framebuffer_context, inject_shader,
                               register_additional_program)
from janim.utils.config import Config

if TYPE_CHECKING:
    from janim.items.effect.frame_effect import FrameEffect


vertex_shader = '''
#version 330 core

in vec2 in_texcoord;

out vec2 v_texcoord;

void main()
{
    gl_Position = vec4(in_texcoord * 2.0 - 1.0, 0.0, 1.0);
    v_texcoord = in_texcoord;
}
'''


class FrameEffectRenderer(Renderer):
    def __init__(self):
        self.initialized: bool = False

    def init(self, fragment_shader: str) -> None:
        self.ctx = Renderer.data_ctx.get().ctx
        self.prog = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=inject_shader('fragment_shader', fragment_shader)
        )
        register_additional_program(self.prog)

        self.u_fbo = self.prog.get('fbo', None)
        if self.u_fbo is not None:
            self.u_fbo.value = 0

        self.fbo = create_framebuffer(self.ctx, Config.get.pixel_width, Config.get.pixel_height)
        self.vbo_texcoords = self.ctx.buffer(
            data=np.array([
                [0.0, 0.0],     # 左上
                [0.0, 1.0],     # 左下
                [1.0, 0.0],     # 右上
                [1.0, 1.0]      # 右下
            ], dtype=np.float32).tobytes()
        )

        self.vao = self.ctx.vertex_array(
            self.prog,
            self.vbo_texcoords,
            'in_texcoord'
        )

    def render(self, item: FrameEffect) -> None:
        if not self.initialized:
            self.init(item.fragment_shader)
            self.initialized = True

        if self.u_fbo is not None:
            import OpenGL.GL as gl

            t = Animation.global_t_ctx.get()

            with blend_context(self.ctx, False), framebuffer_context(self.fbo):
                self.fbo.clear()
                gl.glFlush()
                render_datas = [
                    (appr, appr.stack.compute(t, True))
                    for appr in item.apprs
                    if appr.is_visible_at(t)
                ]
                render_datas.sort(key=lambda x: x[1].depth, reverse=True)
                for appr, data in render_datas:
                    appr.render(data)
                    gl.glFlush()

            self.fbo.color_attachments[0].use(0)

        self.vao.render(mgl.TRIANGLE_STRIP)
