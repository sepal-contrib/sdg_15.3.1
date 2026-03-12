import json
from pathlib import Path
from sepal_ui.scripts.drive_interface import GDriveInterface
import ee
import io
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials

from apiclient import discovery

from component.message import cm
from .gee import search_task

import logging

logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)


class GDrive(GDriveInterface):
    """Extended GDrive interface with additional functionality for 15.3.1 related operations.
    This class extends GDriveInterface to add 15.3.1 specific methods for handling
    Earth Engine exports and rerouting files from Gdrive to SEPAL.
    """

    def __init__(self, sepal_headers=None):
        """Initialize GDrive with SEPAL credentials.

        Args:
            sepal_headers: Optional SEPAL headers dictionary for authentication.
                          If not provided, falls back to file-based credentials.
        """
        super().__init__(sepal_headers)

    def tasks_list(self):
        """For debugging purpose, print the list of all the tasks in gee"""
        service = self.service

        tasks = service.tasks().list(tasklist="@default", q="trashed = false").execute()

        for task in tasks["items"]:
            print(task["title"])

        return

    def print_file_list(self):
        """For debugging purpose, print the list of all the files in the Gdrive"""
        # Override parent method to show more files
        service = self.service

        results = (
            service.files()
            .list(pageSize=50, fields="nextPageToken, files(id, name)")
            .execute()
        )
        items = results.get("files", [])
        if not items:
            print("No files found.")
        else:
            print("Files:")
            for item in items:
                print("{0} ({1})".format(item["name"], item["id"]))

    def get_items(self):
        """Get all the TIFF items in the Gdrive.

        Returns:
            list: Items will have 2 columns, 'name' and 'id'
        """
        service = self.service

        # get list of files
        results = (
            service.files()
            .list(
                q="mimeType='image/tiff' and trashed = false",
                pageSize=1000,
                fields="nextPageToken, files(id, name)",
            )
            .execute()
        )
        items = results.get("files", [])

        return items

    def get_files(self, file_name):
        """Look for the file_name pattern in my Gdrive files and retrieve a list of Ids.

        Args:
            file_name (str): Pattern to search for in file names

        Returns:
            list: List of dictionaries with 'id' and 'name' keys
        """
        items = self.get_items()
        files = []
        for item in items:
            if file_name in item["name"]:
                files.append({"id": item["id"], "name": item["name"]})

        return files

    def download_files(self, files, local_path):
        """Download the files from gdrive to the local_path.

        Args:
            files (list): List of file dictionaries with 'id' and 'name' keys
            local_path (str or Path): Path where files should be saved
        """
        # create path object
        local_path = Path(local_path)

        # open the gdrive service
        service = self.service

        # request the files from gdrive in chunks
        for file in files:
            request = service.files().get_media(fileId=file["id"])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            # write them in a local based file
            with local_path.joinpath(file["name"]).open("wb") as f:
                f.write(fh.getvalue())

    def delete_files(self, files):
        """Delete files from gdrive disk.

        Args:
            files (list): List of file dictionaries with 'id' key
        """
        # open gdrive service
        service = self.service

        # remove the files
        for file in files:
            service.files().delete(fileId=file["id"]).execute()

    def download_to_disk(self, filename, image, aoi_io, output, scale=30, prefix=None):
        """Download the tile to the GEE disk.

        Args:
            filename (str): Description of the file
            image (ee.Image): Image to export
            aoi_io: AOI model with feature_collection attribute
            output: Output widget for messages
            scale (int): Scale in meters for export (default: 30)
            prefix (str): File name prefix for the export

        Returns:
            bool: True if a task is running, False if not
        """

        def launch_task(filename, image, aoi_io, output, scale, prefix):
            """Check if file exists and launch the process if not"""

            download = False

            files = self.get_files(prefix)

            if files == []:
                task_config = {
                    "image": image.clip(aoi_io.feature_collection),
                    "description": filename,
                    "scale": scale,
                    "region": aoi_io.feature_collection.geometry(),
                    "maxPixels": 1e13,
                    "fileNamePrefix": prefix,
                }

                task = ee.batch.Export.image.toDrive(**task_config)
                task.start()
                download = True
            else:
                output.add_live_msg(cm.gdrive.already_done.format(filename), "success")

            return download

        task = search_task(filename)
        if not task:
            download = launch_task(filename, image, aoi_io, output, scale, prefix)
        else:
            if task.state == "RUNNING":
                output.add_live_msg(f"{filename}: {task.state}")
                download = True
            else:
                download = launch_task(filename, image, aoi_io, output, scale, prefix)

        return download
