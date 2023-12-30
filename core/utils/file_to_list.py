def file_to_list(
        filename: str
):
    with open(filename, 'r+') as f:
        return list(filter(bool, f.read().splitlines()))
