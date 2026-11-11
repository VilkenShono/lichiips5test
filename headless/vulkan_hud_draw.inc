        // The overlay's box, against the corner and at the size the settings name, laid out for a
        // picture 1080 rows high and scaled to this one (hud.h, PlaceHud).
        const auto hud_place = Eden::PlaceHud(hud, render_area.width, render_area.height);
        if (hud.width && (hud.loading || hud_place.shown)) {
            const VkRect2D scissor = hud.loading ? VkRect2D{{0, 0}, render_area} :
                VkRect2D{{static_cast<int32_t>(hud_place.box_x), static_cast<int32_t>(hud_place.box_y)},
                         {hud_place.box_w, hud_place.box_h}};
            const VkViewport viewport{static_cast<float>(scissor.offset.x), static_cast<float>(scissor.offset.y),
                static_cast<float>(scissor.extent.width), static_cast<float>(scissor.extent.height), 0, 1};
            cmdbuf.SetViewport(0, viewport);
            cmdbuf.SetScissor(0, scissor);
            cmdbuf.BindPipeline(VK_PIPELINE_BIND_POINT_GRAPHICS, hud_graphics_pipeline);
            auto constants = hud;
            if (hud.loading) {
                // The loading scene fills the picture: tell it how large that is.
                constants.x = render_area.width;
                constants.y = render_area.height;
            } else {
                // Where the text starts in this picture, and the rows its cells are laid out for.
                constants.x = hud_place.text_x;
                constants.y = hud_place.text_y;
                constants.width = hud_place.cell_rows;
            }
            cmdbuf.PushConstants(hud_pipeline_layout, VK_SHADER_STAGE_FRAGMENT_BIT, constants);
            cmdbuf.Draw(4, 1, 0, 0);
        }
