from sepal_ui.aoi import AoiModel
from component.widget import reclassify as rec
from component import parameter as cp


class ReclassifyTile(rec.ReclassifyView):
    def __init__(self, aoi_model: AoiModel):
        super().__init__(
            gee=True,
            default_class={"UNCCD CLASSES": str(cp.utils_dir / "UNCCD.csv")},
            save=True,
            aoi_model=aoi_model,
        )

        # change the title
        self.title.children[0].children = ["Adapt Land Cover map"]

        # remove the custom option
        # tmp_list = self.w_default.children.copy()
        # self.w_default.children = tmp_list[1:]

        # select IPCC by default
        self.w_default.children[1].fire_event("click", None)

        # remove optional panel
        self.w_optional.class_ = "d-none"

        # change the metadata of the tile
        self._metadata = {"mount_id": "reclassify_tile"}

        # clean w_image image type to have only image
        # TODO, uncomment when the sepal_ui lib method will be available
        # self.w_image.types = ["IMAGE"]
        # self.w_image._get_items()
