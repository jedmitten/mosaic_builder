import mosaic_builder as mb


IMAGE_PATH = mb.get_gallery_dir()


def main():
    print(mb.collection.fetch_image_files_from_path(IMAGE_PATH))


if __name__ == "__main__":
    main()
    