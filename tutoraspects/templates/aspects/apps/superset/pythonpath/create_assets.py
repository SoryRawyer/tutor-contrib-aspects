"""Import a list of assets from a yaml file and create them in the superset assets folder."""
import os
import uuid
import yaml
from zipfile import ZipFile
from superset.app import create_app

app = create_app()
app.app_context().push()

from superset import security_manager
from superset.commands.importers.v1.assets import ImportAssetsCommand
from superset.commands.importers.v1.utils import get_contents_from_bundle
from superset.extensions import db
from superset.models.dashboard import Dashboard
from superset.utils.database import get_or_create_db

from copy import deepcopy

BASE_DIR = "/app/assets/superset"

ASSET_FOLDER_MAPPING = {
    "dashboard_title": "dashboards",
    "slice_name": "charts",
    "database_name": "databases",
    "table_name": "datasets",
}

for folder in ASSET_FOLDER_MAPPING.values():
    os.makedirs(f"{BASE_DIR}/{folder}", exist_ok=True)

FILE_NAME_ATTRIBUTE = "_file_name"

TRANSLATIONS_FILE_PATH = "/app/pythonpath/locale.yaml"
ASSETS_FILE_PATH = "/app/pythonpath/assets.yaml"
ASSETS_ZIP_PATH = "/app/assets/assets.zip"

ASSETS_TRANSLATIONS = yaml.load(open(TRANSLATIONS_FILE_PATH, "r"), Loader=yaml.FullLoader)


def main():
    create_assets()


def create_assets():
    """Create assets from a yaml file."""
    roles = {}
    with open(ASSETS_FILE_PATH, "r") as file:
        extra_assets = yaml.safe_load(file)

        if not extra_assets:
            print("No extra assets to create")
            return

        # For each asset, create a file in the right folder
        for asset in extra_assets:
            if FILE_NAME_ATTRIBUTE not in asset:
                raise Exception(f"Asset {asset} has no {FILE_NAME_ATTRIBUTE}")
            file_name = asset.pop(FILE_NAME_ATTRIBUTE)

            # Find the right folder to create the asset in
            for asset_name, folder in ASSET_FOLDER_MAPPING.items():
                if not asset_name in asset:
                    continue

                write_asset_to_file(asset, asset_name, folder, file_name, roles)
                break

    create_zip_and_import_assets()
    update_dashboard_roles(roles)


def get_uuid5(base_uuid, name):
    """Generate an idempotent uuid."""
    base_uuid = uuid.UUID(base_uuid)
    base_namespace = uuid.uuid5(base_uuid, "superset")
    return uuid.uuid5(base_namespace, name)


def write_asset_to_file(asset, asset_name, folder, file_name, roles):
    """Write an asset to a file and generated translated assets"""
    if folder == "databases":
        # This will fix the URI connection string by setting the right password.
        create_superset_db(asset["database_name"], asset["sqlalchemy_uri"])

    asset_translation = ASSETS_TRANSLATIONS.get(asset.get("uuid"), {})

    for language, title in asset_translation.items():
        updated_asset = generate_translated_asset(
            asset, asset_name, folder, language, title, roles
        )

        path = f"{BASE_DIR}/{folder}/{file_name}-{language}.yaml"
        with open(path, "w") as file:
            yaml.dump(updated_asset, file)

    ## WARNING: Dashboard are assigned a Dummy role which prevents users to
    #           access the original dashboards.
    dashboard_roles = asset.pop("_roles", None)
    if dashboard_roles:
        roles[asset["uuid"]] = [
            security_manager.find_role("Admin")
        ]

    path = f"{BASE_DIR}/{folder}/{file_name}.yaml"
    with open(path, "w") as file:
        yaml.dump(asset, file)


def generate_translated_asset(asset, asset_name, folder, language, title, roles):
    """Generate a translated asset with their elements updated"""
    copy = deepcopy(asset)
    copy["uuid"] = str(get_uuid5(copy["uuid"], language))
    copy[asset_name] = title

    if folder == "dashboards":
        copy["slug"] = f"{copy['slug']}-{language}"

        dashboard_roles = copy.pop("_roles", [])
        translated_dashboard_roles = []

        for role in dashboard_roles:
            translated_dashboard_roles.append(f"{role} - {language}")

        roles[copy["uuid"]] = [
            security_manager.find_role(role) for role in translated_dashboard_roles
        ]

        generate_translated_dashboard_elements(copy, language)
        generate_translated_dashboard_filters(copy, language)
    return copy


def generate_translated_dashboard_elements(copy, language):
    """Generate translated elements for a dashboard"""
    position = copy.get("position", {})

    for element in position.values():
        if not isinstance(element, dict):
            continue

        meta = element.get("meta", {})
        original_uuid = meta.get("uuid", None)

        element_type = element.get("type", "Unknown")

        translation, element_type, element_id = None, None, None

        if original_uuid:
            if not original_uuid in ASSETS_TRANSLATIONS:
                print(f"Chart {meta['uuid']} not found in translations")
                continue

            element_type = "Chart"
            element_id = str(get_uuid5(original_uuid, language))
            translation = ASSETS_TRANSLATIONS.get(original_uuid, {}).get(
                language, meta["sliceName"]
            )

            meta["sliceName"] = translation
            meta["uuid"] = element_id

        elif element.get("type") == "TAB":
            chart_body_id = element.get("id")
            if not meta or not meta.get("text"):
                continue

            if not chart_body_id in ASSETS_TRANSLATIONS:
                print(f"Tab {chart_body_id} not found in translations")
                continue

            element_type = "Tab"
            element_id = chart_body_id
            translation = ASSETS_TRANSLATIONS.get(chart_body_id, {}).get(
                language, meta["text"]
            )

            meta["text"] = translation

        if translation and element_type and element_id:
            print(
                f"Generating {element_type} {element_id} for language {language} {translation}"
            )


def generate_translated_dashboard_filters(copy, language):
    """Generate translated filters for a dashboard"""
    metadata = copy.get("metadata", {})

    for filter in metadata.get("native_filter_configuration", []):
        element_type = "Filter"
        element_id = filter["id"]
        translation = ASSETS_TRANSLATIONS.get(element_id, {}).get(
            language, filter["name"]
        )

        filter["name"] = translation
        print(
            f"Generating {element_type} {element_id} for language {language} {translation}"
        )


def create_superset_db(database_name, uri) -> None:
    """Create a database object with the right URI"""
    superset_db = get_or_create_db(database_name, uri, always_create=True)
    db.session.add(superset_db)
    db.session.commit()


def create_zip_and_import_assets():
    """Create a zip file with all the assets and import them in superset"""
    with ZipFile(ASSETS_ZIP_PATH, "w") as zip:
        for folder in ASSET_FOLDER_MAPPING.values():
            for file_name in os.listdir(f"{BASE_DIR}/{folder}"):
                zip.write(
                    f"{BASE_DIR}/{folder}/{file_name}", f"import/{folder}/{file_name}"
                )
        zip.write(f"{BASE_DIR}/metadata.yaml", "import/metadata.yaml")
        contents = get_contents_from_bundle(zip)
        command = ImportAssetsCommand(contents)
        command.run()

    os.remove(ASSETS_ZIP_PATH)


def update_dashboard_roles(roles):
    """Update the roles of the dashboards"""
    for dashboard_uuid, role_ids in roles.items():
        dashboard = db.session.query(Dashboard).filter_by(uuid=dashboard_uuid).one()
        dashboard.roles = role_ids
        dashboard.published = True
        db.session.commit()


if __name__ == "__main__":
    main()
